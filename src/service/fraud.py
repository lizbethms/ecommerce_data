"""Etapa 6: señales verificadas e idempotencia, compartidas por HTTP y CLI."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import threading

from src.data.schema import utc, validate
from src.structures.probabilistic import BloomFilter, CountMinSketch, WindowCounts
from .history import CSVHistory, PersistenceError

DEFAULT_CONFIG = dict(capacity=1000, false_positive_rate=0.01,
                      epsilon=0.01, delta=0.001, threshold=20)
ENTITY_TYPES = {'cuenta': 'account', 'dispositivo': 'device', 'medio_pago': 'payment'}
IGNORED = {'ingested_at', 'scenario_id', 'is_injected_duplicate', 'is_injected_anomaly',
           'generation_run_id', 'synthetic_fields', 'quality_flags', 'source_row_id', 'event_origin'}


class ConflictError(Exception):
    pass


def canonical(event, payment=False):
    # Un intento reenviado puede tener otro event_id, pero no otro contenido.
    excluded = IGNORED | ({'event_id'} if payment else set())
    return json.dumps({k: v for k, v in event.items() if k not in excluded}, sort_keys=True, allow_nan=False)


def minute_time(minute):
    return datetime.fromtimestamp(minute * 60, timezone.utc).isoformat().replace('+00:00', 'Z')


class FraudService:
    def __init__(self, history_path, config=None):
        self.config = dict(DEFAULT_CONFIG)
        if config:
            if set(config) - set(DEFAULT_CONFIG):
                raise ValueError('Configuración desconocida')
            self.config.update(config)
        if type(self.config['capacity']) is not int or type(self.config['threshold']) is not int or self.config['threshold'] <= 0:
            raise ValueError('Capacidad y umbral deben ser enteros positivos')
        self.lock = threading.RLock()
        self.registry = {}
        self.events = {}
        self.payments = {}
        self.stats = Counter()
        self.bloom = BloomFilter(self.config['capacity'], self.config['false_positive_rate'])
        self.windows = WindowCounts(self.config['epsilon'], self.config['delta'])
        # Validar parámetros antes de crear un historial.
        CountMinSketch(self.config['epsilon'], self.config['delta'])
        self.history = CSVHistory(history_path)
        try:
            if not self.history.records:
                self.history.append('configuracion', self.config)
            else:
                operation, config_saved, _ = self.history.records[0]
                if operation != 'configuracion' or config_saved != self.config:
                    raise PersistenceError('Configuración incompatible en fila 2')
                for operation, payload, line in self.history.records[1:]:
                    try:
                        self._apply(operation, payload)
                    except Exception as exc:
                        raise PersistenceError(f'Historial inválido en fila {line}: {exc}') from exc
            self.history.records.clear()
        except Exception:
            self.close()
            raise

    def close(self):
        self.history.close()

    def _rebuild(self):
        capacity = self.config['capacity']
        while capacity < len(self.registry):
            capacity *= 2
        self.bloom = BloomFilter(capacity, self.config['false_positive_rate'])
        for key in self.registry:
            self.bloom.add(key)

    @staticmethod
    def entity_key(kind, identifier):
        if kind not in ENTITY_TYPES or not isinstance(identifier, str) or not identifier.strip():
            raise ValueError('Tipo o identificador de entidad inválido')
        return ENTITY_TYPES[kind] + ':' + identifier

    def change_entity(self, kind, identifier, reason=None):
        self.entity_key(kind, identifier)
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            raise ValueError('Motivo requerido')
        payload = dict(tipo=kind, identificador=identifier, motivo=reason)
        with self.lock:
            self.history.append('entidad', payload)
            self._apply('entidad', payload)
        return payload

    def entities(self):
        with self.lock:
            return [dict(tipo=kind, identificador=key.split(':', 1)[1], motivo=reason)
                    for key, reason in sorted(self.registry.items())
                    for kind, prefix in ENTITY_TYPES.items() if key.startswith(prefix + ':')]

    def _apply(self, operation, payload):
        if operation == 'entidad':
            key = self.entity_key(payload['tipo'], payload['identificador'])
            if payload['motivo'] is None:
                self.registry.pop(key, None)
            else:
                if not isinstance(payload['motivo'], str) or not payload['motivo'].strip():
                    raise ValueError('Motivo requerido')
                self.registry[key] = payload['motivo']
            self._rebuild()
        elif operation == 'evento':
            event = self._validate(payload)
            self._check_conflict(event)
            return self._process(event)
        else:
            raise ValueError('Operación desconocida')

    @staticmethod
    def _validate(event):
        if not isinstance(event, dict):
            raise ValueError('Evento debe ser un objeto')
        event = deepcopy(event)
        try:
            validate(event)
            event['event_time'] = utc(event['event_time'])
            minute = int(datetime.fromisoformat(event['event_time'].replace('Z', '+00:00')).timestamp() // 60)
            # Validar los límites antes de persistir: ninguna ventana puede salir del calendario.
            minute_time(minute - 4)
            minute_time(minute + 1)
            canonical(event)
        except (KeyError, TypeError, AttributeError, OverflowError) as exc:
            raise ValueError(f'Evento inválido: {exc}') from exc
        return event

    def _check_conflict(self, event):
        previous = self.events.get(event['event_id'])
        if previous and previous[0] != canonical(event):
            raise ConflictError('event_id reutilizado con contenido diferente')
        if event['event_type'] == 'payment_attempt':
            previous = self.payments.get(event['payment_attempt_id'])
            if previous and previous[0] != canonical(event, payment=True):
                raise ConflictError('payment_attempt_id reutilizado con contenido diferente')

    def process(self, event):
        event = self._validate(event)
        with self.lock:
            self._check_conflict(event)
            self.history.append('evento', event)
            return deepcopy(self._process(event))

    def _process(self, event):
        event_id = event['event_id']
        previous = self.events.get(event_id)
        if not previous and event['event_type'] == 'payment_attempt':
            previous = self.payments.get(event['payment_attempt_id'])
        self.stats['received'] += 1
        if previous:
            self.stats['duplicates'] += 1
            result = deepcopy(previous[1])
            result.update(event_id=event_id, status='duplicate')
            self.events[event_id] = (canonical(event), result)
            return result
        minute = int(datetime.fromisoformat(event['event_time'].replace('Z', '+00:00')).timestamp() // 60)
        self.windows.advance(minute)
        signals = dict(memberships=[], frequency=None, decision='continue', reasons=[])
        result = dict(event_id=event_id, status='not_applicable', risk_signals=signals)
        if event['event_type'] == 'payment_attempt':
            result['status'] = 'processed'
            for prefix, field in [('account', 'user_id'), ('device', 'device_id'), ('payment', 'payment_method_id')]:
                key = f'{prefix}:{event[field]}'
                positive = self.bloom.contains(key)
                confirmed = positive and key in self.registry
                self.stats['bloom_queries'] += 1
                self.stats['bloom_positives'] += int(positive)
                self.stats['bloom_false_positives'] += int(positive and not confirmed)
                signals['memberships'].append(dict(key=key, bloom_positive=positive, verified=confirmed,
                                                   false_positive=positive and not confirmed))
                if confirmed:
                    signals['reasons'].append('flagged_entity')
            active = self.windows.add(minute, event['device_id'])
            estimate, exact = self.windows.counts(event['device_id'])
            candidate = active and estimate >= self.config['threshold']
            verified = candidate and exact >= self.config['threshold']
            signals['frequency'] = dict(key=event['device_id'], window_start=minute_time(self.windows.minute - 4),
                                       window_end=minute_time(self.windows.minute + 1), estimate=estimate,
                                       exact_count=exact if candidate else None, candidate=candidate,
                                       verified=verified, counted=active)
            if not active:
                result['status'] = 'outside_window'
            if verified:
                signals['reasons'].append('high_frequency')
            if signals['reasons']:
                signals['decision'] = 'review'
                self.stats['reviews'] += 1
            if candidate:
                self.stats['frequency_candidates'] += 1
            self.stats['payment_updates'] += int(active)
            self.payments[event['payment_attempt_id']] = (canonical(event, payment=True), deepcopy(result))
        self.stats['unique_events'] += 1
        self.events[event_id] = (canonical(event), deepcopy(result))
        return result

    def metrics(self):
        with self.lock:
            return dict(configuracion=dict(self.config), contadores=dict(self.stats),
                        minuto_actual=self.windows.minute, entidades=len(self.registry),
                        capacidad_bloom=self.bloom.capacity, ocupacion_bloom=self.bloom.occupancy(),
                        operaciones_persistidas=self.history.sequence,
                        disponible=not self.history.failed)
