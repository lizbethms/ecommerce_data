"""Ingesta y preparación: normaliza, valida, deduplica y despacha (etapas 0–1)."""
from collections import Counter
from datetime import datetime, timezone

from src.data.parquet_io import EVENT_SCHEMA
from src.data.schema import money, stable_id, utc, validate
from src.structures.hash_table import HashTable
from src.structures.sorting import merge_sort

from .base import Servicio

CAMPOS = EVENT_SCHEMA.names
IDENTIFICADORES = ('user_id', 'product_id', 'category_id')
MINUSCULAS = ('event_type', 'category_code', 'brand', 'delivery_type', 'payment_status')
# Campos que no forman parte del contenido de negocio de un evento.
NO_NEGOCIO = {'ingested_at', 'is_injected_duplicate', 'quality_flags', 'priority', 'priority_reason'}


def prioridad(evento):
    """Regla explícita (POLICIES['priority']); nunca consulta etiquetas de evaluación."""
    if evento['event_type'] == 'payment_attempt' and evento['payment_status'] == 'failed':
        return 100, 'failed_payment'
    if evento['delivery_type'] == 'express':
        return 10, 'express_delivery'
    return 0, 'normal'


def normalizar(crudo):
    evento = {campo: None for campo in CAMPOS}
    evento.update(schema_version='1.0', synthetic_fields=[], quality_flags=[],
                  is_injected_duplicate=False, is_injected_anomaly=False)
    for campo, valor in crudo.items():
        if campo not in evento or valor is None:
            continue
        if isinstance(valor, str):
            valor = valor.strip() or None
        evento[campo] = valor
    for campo in IDENTIFICADORES:
        if evento[campo] is not None:
            evento[campo] = str(evento[campo])
    for campo in MINUSCULAS:
        if isinstance(evento[campo], str):
            evento[campo] = evento[campo].lower()
    if not evento['event_time']:
        raise ValueError('Fecha del evento requerida')
    try:
        evento['event_time'] = utc(evento['event_time'])
        if evento['scheduled_at']:
            evento['scheduled_at'] = utc(evento['scheduled_at'])
    except ValueError as error:
        raise ValueError(f'Fecha inválida: {error}') from None
    if evento['price'] is not None:
        evento['price'] = money(str(evento['price']))
    for campo in ('quantity', 'rating'):
        if evento[campo] is not None:
            evento[campo] = int(evento[campo])
    if evento['event_type'] == 'purchase' and evento['quantity'] is None:
        evento['quantity'] = 1
    evento['priority'], evento['priority_reason'] = prioridad(evento)
    evento['ingested_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    if evento['price'] == '0.00' and 'zero_price_review' not in evento['quality_flags']:
        evento['quality_flags'] = list(evento['quality_flags']) + ['zero_price_review']
    return evento


def huella(evento):
    return stable_id(*(evento.get(c) for c in CAMPOS if c not in NO_NEGOCIO))


class ServicioIngesta(Servicio):
    nombre = 'ingesta'

    def __init__(self, config, suscriptores):
        super().__init__(config)
        self.suscriptores = list(suscriptores)
        self.vistos = HashTable(4096)  # event_id -> huella del contenido
        self.aceptados = self.duplicados = self.lotes = 0
        self.rechazos = Counter()

    def procesar(self, evento, contexto):
        return self.recibir_lote([evento])[0]

    def _preparar(self, crudo):
        try:
            evento = normalizar(crudo)
            validate(evento)
            return evento, None
        except ValueError as error:
            return None, str(error)
        except (TypeError, KeyError):
            return None, 'Campo requerido ausente o con tipo inválido'

    def recibir_lote(self, crudos):
        """Procesa un lote. Devuelve un resultado por evento, en el orden recibido."""
        self.lotes += 1
        resultados = [None] * len(crudos)
        validos = []
        for indice, crudo in enumerate(crudos):
            evento, motivo = self._preparar(crudo)
            if motivo:
                self.rechazos[motivo] += 1
                resultados[indice] = {'event_id': crudo.get('event_id'), 'estado': 'rechazado', 'motivo': motivo}
            else:
                validos.append((indice, evento, huella(evento)))
        # Etapa 1: ordenar el lote por identidad deja los repetidos adyacentes (orden
        # estable: gana el primero recibido). Los lotes anteriores se consultan en la tabla hash.
        anterior = None
        nuevos = []
        for indice, evento, firma in merge_sort(validos, key=lambda item: item[1]['event_id']):
            if anterior and anterior[0] == evento['event_id']:
                conocido = anterior[1]
            else:
                conocido = self.vistos.get(evento['event_id'])
            anterior = (evento['event_id'], conocido or firma)
            if conocido is not None:
                estado = 'duplicado' if conocido == firma else 'rechazado'
                motivo = None if estado == 'duplicado' else 'identidad repetida con contenido distinto'
                if estado == 'duplicado':
                    self.duplicados += 1
                else:
                    self.rechazos[motivo] += 1
                resultados[indice] = {'event_id': evento['event_id'], 'estado': estado, 'motivo': motivo}
            else:
                nuevos.append((indice, evento, firma))
        for _, evento, firma in nuevos:
            self.vistos[evento['event_id']] = firma
        # Los aceptados se despachan en orden temporal; el desempate es el orden de llegada.
        for indice, evento, _ in merge_sort(nuevos, key=lambda item: (item[1]['event_time'], item[0])):
            contexto, servicios = {}, []
            for servicio in self.suscriptores:
                if servicio.acepta(evento):
                    servicios.append(servicio.nombre)
                    salida = servicio.recibir(evento, contexto)
                    if salida is not None:
                        contexto[servicio.nombre] = salida
            self.aceptados += 1
            self.procesados += 1
            resultados[indice] = {'event_id': evento['event_id'], 'estado': 'aceptado',
                                  'prioridad': evento['priority'], 'servicios': servicios, 'resultados': contexto}
        return resultados

    def estadisticas(self):
        return dict(lotes=self.lotes, aceptados=self.aceptados, duplicados=self.duplicados,
                    rechazados=sum(self.rechazos.values()), motivos_rechazo=dict(self.rechazos.most_common(10)),
                    ids_registrados=len(self.vistos))
