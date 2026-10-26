import csv
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.fraud import create_app, translate
from src.data.prepare import prepare
from src.pipeline.stage6 import load_entities, run_stage6
from src.service.fraud import FraudService, ConflictError
from src.service.history import PersistenceError
from src.structures.probabilistic import BloomFilter, CountMinSketch
import test_stage0
from test_stage0 import CONFIG

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples/fraude'


def event(index=0, seconds=0, device='device'):
    template = json.loads((EXAMPLES / 'pago_normal.json').read_text())['evento']
    template.update(event_id=f'event:{index}', payment_attempt_id=f'attempt:{index}', device_id=device,
                    event_time=(datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)).isoformat())
    return template


class FraudTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / 'history.csv'
        self.service = FraudService(self.path)

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def test_membership_false_positive_and_rebuild(self):
        bloom = BloomFilter()
        for i in range(100):
            bloom.add(str(i))
        self.assertTrue(all(bloom.contains(str(i)) for i in range(100)))
        with patch.object(self.service.bloom, 'contains', return_value=True):
            result = self.service.process(event())
        self.assertEqual(result['risk_signals']['decision'], 'continue')
        self.assertEqual(self.service.stats['bloom_false_positives'], 3)
        self.service.change_entity('dispositivo', 'device', 'Prueba, con comillas " y\nsalto')
        self.assertEqual(self.service.process(event(1))['risk_signals']['decision'], 'review')
        self.service.change_entity('dispositivo', 'device')
        self.assertFalse(self.service.bloom.contains('device:device'))
        self.assertEqual(self.service.process(event(2))['risk_signals']['decision'], 'continue')

    def test_threshold_duplicates_conflicts_and_recovery(self):
        for index in range(19):
            result = self.service.process(event(index))
        self.assertEqual(result['risk_signals']['decision'], 'continue')
        result = self.service.process(event(19))
        self.assertEqual(result['risk_signals']['frequency']['exact_count'], 20)
        self.assertEqual(result['risk_signals']['decision'], 'review')
        duplicate = self.service.process(dict(event(19), is_injected_duplicate=True, ingested_at='anything'))
        self.assertEqual(duplicate['status'], 'duplicate')
        alias = dict(event(19), event_id='alias')
        self.assertEqual(self.service.process(alias)['status'], 'duplicate')
        self.assertEqual(self.service.windows.counts('device'), (20, 20))
        with self.assertRaises(ConflictError):
            self.service.process(dict(alias, device_id='other'))
        with self.assertRaises(ConflictError):
            self.service.process(dict(event(19), payment_attempt_id='changed'))
        before = self.service.metrics()
        self.service.close()
        self.service = FraudService(self.path)
        self.assertEqual(before, self.service.metrics())
        self.assertEqual(self.service.process(alias)['status'], 'duplicate')

    def test_expiration_late_events_and_non_payment_clock(self):
        self.service.process(event(0))
        self.service.process(event(1, 240))
        self.service.process(event(2, 60))
        self.assertEqual(self.service.windows.counts('device'), (3, 3))
        self.service.process(event(3, 300))
        self.assertEqual(self.service.windows.counts('device'), (3, 3))
        late = self.service.process(event(4, 59))
        self.assertEqual(late['status'], 'outside_window')
        self.assertEqual(self.service.windows.counts('device'), (3, 3))
        self.service.process(dict(event(5, 900), event_type='view'))
        self.assertEqual(self.service.windows.counts('device'), (0, 0))
        self.assertEqual(self.service.process(event(6, 900))['risk_signals']['frequency']['estimate'], 1)

    def test_cms_collision_requires_confirmation(self):
        # Un solo casillero por fila fuerza colisiones reales entre claves.
        with patch('src.structures.probabilistic.indices', side_effect=lambda key, width, depth: iter([0] * depth)):
            for index in range(20):
                self.service.process(event(index, device='hot'))
            result = self.service.process(event(21, device='cold'))
        frequency = result['risk_signals']['frequency']
        self.assertEqual(frequency['estimate'], 21)
        self.assertEqual(frequency['exact_count'], 1)
        self.assertFalse(frequency['verified'])
        self.assertEqual(result['risk_signals']['decision'], 'continue')

    def test_exclusive_history_corruption_and_config(self):
        with self.assertRaises(PersistenceError):
            FraudService(self.path)
        self.service.process(event())
        self.service.close()
        with self.assertRaises(PersistenceError):
            FraudService(self.path, {'threshold': 21})
        with self.path.open('a') as stream:
            stream.write('incomplete')
        with self.assertRaisesRegex(PersistenceError, 'fila'):
            FraudService(self.path)

    def test_persistence_failure_does_not_apply(self):
        with patch.object(self.service.history, 'sync', side_effect=OSError('disco')):
            with self.assertRaises(PersistenceError):
                self.service.process(event())
        self.assertFalse(self.service.events)
        with self.assertRaises(PersistenceError):
            self.service.process(event(1))

    def test_invalid_inputs_and_capacity_growth(self):
        for invalid in [dict(event(), event_id=1), dict(event(), device_id=2),
                        dict(event(), event_time='2026-01-01'), dict(event(), payment_status='unknown'),
                        dict(event(), payment_status=[]), dict(event(), price='1e999'),
                        dict(event(), event_time='9999-12-31T23:59:59Z'), {}, []]:
            with self.assertRaises(ValueError):
                self.service.process(invalid)
        self.assertEqual(self.service.history.sequence, 1)
        small = FraudService(self.root / 'small.csv', {'capacity': 1})
        try:
            small.change_entity('cuenta', 'one', 'Prueba')
            small.change_entity('cuenta', 'two', 'Prueba')
            self.assertEqual(small.bloom.capacity, 2)
            self.assertTrue(small.bloom.contains('account:one'))
            self.assertTrue(small.bloom.contains('account:two'))
        finally:
            small.close()

    def test_checksum_corruption_and_api_restart(self):
        path = self.root / 'restart.csv'
        with TestClient(create_app(path)) as client:
            original = client.post('/fraude/eventos', json={'evento': event()}).json()
        with TestClient(create_app(path)) as client:
            recovered = client.post('/fraude/eventos', json={'evento': event()}).json()
            self.assertEqual(recovered['estado'], 'duplicado')
            self.assertEqual(original['senales_riesgo'], recovered['senales_riesgo'])
        content = path.read_text()
        path.write_text(content.replace('event:0', 'event:1'))
        with self.assertRaisesRegex(PersistenceError, 'fila'):
            FraudService(path)

    def test_api_errors_and_examples(self):
        expected = json.loads((EXAMPLES / 'resultados_esperados.json').read_text())
        events = [json.loads(line) for line in (EXAMPLES / 'eventos.jsonl').read_text().splitlines()]
        with TestClient(create_app(self.root / 'api.csv')) as client:
            self.assertEqual(client.get('/fraude/salud').status_code, 200)
            with (EXAMPLES / 'entidades.csv').open() as stream:
                for row in csv.DictReader(stream):
                    response = client.put(f"/fraude/entidades/{row['tipo']}/{row['identificador']}", json={'motivo': row['motivo']})
                    self.assertEqual(response.status_code, 200)
            load_entities(self.service, EXAMPLES / 'entidades.csv')
            for item, wanted in zip(events, expected):
                response = client.post('/fraude/eventos', json={'evento': item})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result, translate(self.service.process(item)))
                self.assertEqual(result['evento_id'], wanted['evento_id'])
                self.assertEqual(result['estado'], wanted['estado'])
                self.assertEqual(result['senales_riesgo']['decision'], wanted['decision'])
                for field in ('estimacion', 'conteo_exacto'):
                    self.assertEqual(result['senales_riesgo']['frecuencia'][field], wanted[field])
            for filename, code in [('pago_invalido.json', 422), ('pago_conflictivo.json', 409)]:
                self.assertEqual(client.post('/fraude/eventos', json=json.loads((EXAMPLES / filename).read_text())).status_code, code)
            self.assertEqual(client.put('/fraude/entidades/otro/id', json={'motivo': 'x'}).status_code, 422)
            self.assertEqual(len(client.get('/fraude/entidades').json()), 3)
            self.assertEqual(client.delete('/fraude/entidades/dispositivo/syn:example:flagged').status_code, 200)
            with patch.object(client.app.state.service.history, 'sync', side_effect=OSError('disco')):
                self.assertEqual(client.post('/fraude/eventos', json={'evento': event(100)}).status_code, 503)
            self.assertEqual(client.get('/fraude/salud').status_code, 503)

    def test_batch_preserves_envelopes_and_recovers(self):
        record = dict(event=event(), event_id='event:0', stage_results={'0': {'status': 'emitted'}},
                      processing_times={'0': 'previous'})
        source = self.root / 'input.jsonl'
        source.write_text(json.dumps(record) + '\n')
        metrics = run_stage6(source, self.root / 'out.jsonl', self.root / 'batch.csv')
        out = json.loads((self.root / 'out.jsonl').read_text())
        self.assertEqual(out['stage_results']['0'], record['stage_results']['0'])
        self.assertIn('6', out['stage_results'])
        self.assertEqual(metrics['eventos_procesados'], 1)
        metrics = run_stage6(source, self.root / 'out2.jsonl', self.root / 'batch.csv')
        self.assertEqual(metrics['contadores']['duplicates'], 1)


class Stage6PreparationTests(unittest.TestCase):
    setUp = test_stage0.PreparationTests.setUp
    tearDown = test_stage0.PreparationTests.tearDown

    def test_stage6_profile_reproducible(self):
        first = self.root / 'fraud1'
        second = self.root / 'fraud2'
        for path in (first, second):
            manifest = prepare(self.source, path, 60, CONFIG, profile='stage6')
            self.assertEqual(manifest['counts']['total'], 60)
            self.assertEqual(manifest['counts']['by_origin']['synthetic'], 39)
            self.assertEqual(manifest['validation']['verified_duplicate_resends'], 2)
        self.assertEqual((first / 'events.jsonl').read_bytes(), (second / 'events.jsonl').read_bytes())
        metrics = run_stage6(first / 'events.jsonl', self.root / 'results.jsonl', self.root / 'run.csv',
                             entities_path=first / 'entidades.csv')
        self.assertEqual(metrics['contadores']['duplicates'], 2)
        self.assertGreaterEqual(metrics['contadores']['reviews'], 10)
