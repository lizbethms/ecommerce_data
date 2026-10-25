"""Muestra por sesiones -> preparación Parquet -> mismo contrato que JSONL -> replay."""
import asyncio
import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyarrow.parquet as pq

from src.data.parquet_io import EVENT_SCHEMA, iter_events
from src.data.prepare import prepare
from src.data.sample import sample_sessions
from src.data.schema import SOURCE_COLUMNS, validate
from src.pipeline.stage0 import run_stage0

CONFIG = dict(seed=7, chunk_size=16, order_window_minutes=30, queue_capacity=8, rate=10000,
              burst_size=10, burst_interval=0.0, historical_speed=3600)
SYNTHETIC = dict(n_orders=6, n_browse_sessions=3, n_fraud_bursts=2, n_flagged=2, n_resends=3,
                 p_return=0.5, p_review=0.5)
CATEGORIAS = ['electronics.smartphone', 'electronics.audio.headphone', 'appliances.kitchen.kettle', '']


def fuente(path):
    """CSV REES46 pequeño: 30 sesiones, algunas con compras de varios productos."""
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(SOURCE_COLUMNS)
        segundo = 0
        for sesion in range(30):
            for paso in range(4):
                producto = 1000 + (sesion * 3 + paso) % 12
                tipo = 'purchase' if sesion % 3 == 0 and paso >= 2 else 'view'
                writer.writerow([f'2019-10-01 00:{segundo // 60:02d}:{segundo % 60:02d} UTC', tipo, producto,
                                 2000 + producto % 4, CATEGORIAS[producto % 4], 'marca' if producto % 2 else '',
                                 f'{producto % 50 + 0.99:.2f}', 500 + sesion, f'sess-{sesion}'])
                segundo += 7


class TestSampleParquet(unittest.TestCase):
    def test_sample_prepare_roundtrip_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fuente(tmp / 'source.csv')
            info = sample_sessions(tmp / 'source.csv', tmp / 'sample.csv', target_rows=60, window_rows=120,
                                   seed=1, guard_minutes=1)
            self.assertLessEqual(info['rows_written'], 60)
            self.assertGreater(info['by_type'].get('purchase', 0), 0)
            manifest = prepare(tmp / 'sample.csv', tmp / 'out', None, CONFIG, 'parquet', SYNTHETIC)
            self.assertTrue(manifest['validation']['passed'])
            self.assertIn('events.parquet', manifest['artifacts'])
            self.assertEqual(pq.read_schema(tmp / 'out/events.parquet'), EVENT_SCHEMA)
            for tabla in ('catalog', 'orders', 'inventory', 'purchases', 'payments', 'flags'):
                self.assertTrue((tmp / f'out/{tabla}.parquet').exists())
            with closing(sqlite3.connect(tmp / 'out/entities.sqlite')) as db:
                originales = [json.loads(p) for (p,) in db.execute('SELECT payload FROM events ORDER BY time,seq')]
            leidos = list(iter_events(tmp / 'out/events.parquet'))
            self.assertEqual(leidos, originales)
            for e in leidos:
                validate(e)
            tipos = {e['event_type'] for e in leidos}
            self.assertTrue({'search', 'payment_attempt', 'return', 'review', 'purchase'} <= tipos)
            stats = asyncio.run(run_stage0(tmp / 'out/events.parquet', tmp / 'replay.jsonl', CONFIG))
            self.assertEqual(stats['consumed'], len(leidos))


if __name__ == '__main__':
    unittest.main()
