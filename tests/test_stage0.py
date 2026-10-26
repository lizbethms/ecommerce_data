import asyncio
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.data.prepare import Writer, connect, digest_file, prepare
from src.data.schema import SOURCE_COLUMNS, money
from src.pipeline.stage0 import run_stage0
from src.structures.fifo import BoundedFIFO

CONFIG = dict(seed=2026, chunk_size=3, order_window_minutes=30, queue_capacity=2,
              rate=100000, burst_size=3, burst_interval=0.0001, historical_speed=100000)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.csv'
        with self.source.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(SOURCE_COLUMNS)
            for i in range(30):
                writer.writerow(['2019-10-01 00:00:00 UTC', 'purchase' if i in (0, 2, 4) else 'view',
                                 str(i % 2 + 1), '9999999999999999999', '', '',
                                 '0.00' if i % 2 else '12.30', '42', '' if i == 2 else 'session'])

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, name='prepared', size=30):
        out = self.root / name
        manifest = prepare(self.source, out, size, CONFIG)
        events = [json.loads(line) for line in (out / 'events.jsonl').read_text().splitlines()]
        return out, manifest, events

    def test_reproducible_quality_and_dependencies(self):
        original_hash = digest_file(self.source)
        first, manifest, events = self.prepare()
        second, other, _ = self.prepare('again')
        self.assertEqual(digest_file(self.source), original_hash)
        self.assertEqual((first / 'events.jsonl').read_bytes(), (second / 'events.jsonl').read_bytes())
        self.assertEqual(manifest['generation_run_id'], other['generation_run_id'])
        self.assertEqual(len(events), 30)
        self.assertEqual(manifest['counts']['by_origin'], {'real': 17, 'synthetic': 13})
        self.assertGreater(manifest['counts']['source_duplicate_candidates'], 0)
        self.assertEqual(manifest['counts']['missing_sessions_isolated'], 1)
        self.assertEqual([e['event_time'] for e in events], sorted(e['event_time'] for e in events))
        real = [e for e in events if e['event_origin'] == 'real']
        self.assertEqual(len({e['event_id'] for e in real}), len(real))
        self.assertTrue(all(e['category_id'] == '9999999999999999999' for e in real))
        self.assertTrue(any('zero_price_review' in e['quality_flags'] for e in real))
        self.assertTrue(any(e['user_session'].startswith('syn:missing-session:') for e in real))
        purchases = {e['event_id']: e for e in events if e['event_type'] == 'purchase'}
        returned = next(e for e in events if e['event_type'] == 'return')
        purchase = purchases[returned['original_purchase_event_id']]
        self.assertGreaterEqual(returned['event_time'], purchase['event_time'])
        self.assertLessEqual(returned['quantity'], purchase['quantity'])
        self.assertEqual(manifest['validation']['verified_duplicate_resends'], 1)
        with sqlite3.connect(first / 'entities.sqlite') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM inventory WHERE stock<0 OR stock!=supplied-purchased+returned').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(DISTINCT product_id) FROM purchases WHERE order_id=?", (purchase['order_id'],)).fetchone()[0], 2)

    def test_full_source_and_stable_ids_across_sizes(self):
        _, _, prefix = self.prepare()
        _, manifest, full = self.prepare('master', None)
        self.assertEqual(manifest['counts']['total'], 43)
        self.assertEqual(manifest['source']['rows_selected'], 30)
        self.assertFalse(manifest['selection']['prefix_may_cut_sessions_or_orders'])
        self.assertEqual([e['event_id'] for e in prefix if e['event_origin'] == 'real'],
                         [e['event_id'] for e in full if e['event_origin'] == 'real'][:17])

    def test_invalid_return_rejected(self):
        _, _, events = self.prepare()
        db = connect(self.root / 'invalid.sqlite')
        try:
            writer = Writer(db)
            returned = next(e for e in events if e['event_type'] == 'return')
            with self.assertRaisesRegex(ValueError, 'Devolución'):
                writer.add(returned)
        finally:
            db.close()

    def test_excessive_or_early_return_and_unpaid_purchase(self):
        _, _, events = self.prepare()
        db = connect(self.root / 'cycle.sqlite')
        try:
            writer = Writer(db)
            returned = next(e for e in events if e['event_type'] == 'return')
            for event in events:
                if event['event_type'] == 'return':
                    break
                writer.add(event)
            invalid = dict(returned, quantity=100)
            with self.assertRaisesRegex(ValueError, 'Devolución'):
                writer.add(invalid)
            invalid = dict(returned, event_time='2018-01-01T00:00:00Z')
            with self.assertRaisesRegex(ValueError, 'Devolución'):
                writer.add(invalid)
            invalid = dict(next(e for e in events if e['event_origin'] == 'synthetic' and e['event_type'] == 'purchase'),
                           event_id='syn:unpaid', order_id='syn:missing-payment')
            with self.assertRaisesRegex(ValueError, 'pago exitoso'):
                writer.add(invalid)
        finally:
            db.close()

    def test_reject_invalid_source_and_no_overwrite(self):
        self.prepare()
        with self.assertRaises(FileExistsError):
            self.prepare()
        for value in ('-1', 'NaN', 'Infinity', '1.001'):
            with self.assertRaises(ValueError):
                money(value)

    def test_replay_modes_fifo_and_error_propagation(self):
        prepared, _, events = self.prepare()
        async def check():
            for mode in ('unlimited', 'constant', 'burst', 'historical'):
                output = self.root / f'{mode}.jsonl'
                stats = await run_stage0(prepared / 'events.jsonl', output, CONFIG, mode, 0.0001)
                emitted = [json.loads(line) for line in output.read_text().splitlines()]
                self.assertEqual([x['event_id'] for x in emitted], [x['event_id'] for x in events])
                self.assertTrue(all(x['event']['ingested_at'] for x in emitted))
                self.assertEqual(stats['produced'], stats['consumed'])
                self.assertTrue(stats['fifo_drained'])
                self.assertLessEqual(stats['queue_peak'], CONFIG['queue_capacity'])
                self.assertGreater(stats['blocked_puts'], 0)
            malformed = self.root / 'bad.jsonl'
            malformed.write_text('{bad json}\n')
            with self.assertRaises(ExceptionGroup):
                await asyncio.wait_for(run_stage0(malformed, self.root / 'bad-out.jsonl', CONFIG), 2)
        asyncio.run(check())


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_backpressure(self):
        queue = BoundedFIFO(1)
        await queue.put('first')
        pending = asyncio.create_task(queue.put('second'))
        await asyncio.sleep(0)
        self.assertFalse(pending.done())
        self.assertEqual(await queue.get(), 'first')
        queue.task_done()
        await pending
        self.assertEqual(await queue.get(), 'second')
        queue.task_done()
        await queue.join()
        self.assertEqual(queue.peak_size, 1)
        with self.assertRaises(ValueError):
            BoundedFIFO(0)


if __name__ == '__main__':
    unittest.main()
