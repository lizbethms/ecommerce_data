"""Preparación en disco; la memoria depende del bloque, no del dataset."""
import csv
import hashlib
import json
import platform
import random
import sqlite3
from itertools import count
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .schema import SOURCE_COLUMNS, money, stable_id, utc, validate


def digest_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def connect(path):
    db = sqlite3.connect(path)
    db.executescript('''
        PRAGMA cache_size=-8192;
        PRAGMA temp_store=FILE;
        CREATE TABLE events(seq INTEGER PRIMARY KEY, event_id TEXT, time TEXT, payload TEXT);
        CREATE TABLE fingerprints(fingerprint TEXT PRIMARY KEY, first_row INTEGER);
        CREATE TABLE catalog(product_id TEXT PRIMARY KEY, category_id TEXT,
          category_code TEXT, brand TEXT, last_observed_price TEXT, observed_at TEXT);
        CREATE TABLE orders(order_id TEXT PRIMARY KEY, user_id TEXT, user_session TEXT,
          delivery_type TEXT, scheduled_at TEXT, grouping_rule TEXT, origin TEXT);
        CREATE TABLE inventory(product_id TEXT PRIMARY KEY, stock INTEGER DEFAULT 0,
          supplied INTEGER DEFAULT 0, purchased INTEGER DEFAULT 0, returned INTEGER DEFAULT 0);
        CREATE TABLE purchases(event_id TEXT PRIMARY KEY, order_id TEXT, product_id TEXT,
          user_id TEXT, time TEXT, quantity INTEGER, returned INTEGER DEFAULT 0);
        CREATE TABLE payments(order_id TEXT PRIMARY KEY, success_time TEXT);
    ''')
    return db


class Writer:
    def __init__(self, db):
        self.db = db
        self.types = Counter()
        self.origins = Counter()
        self.quality = Counter()
        self.count = 0

    def add(self, event):
        validate(event)
        db = self.db
        # Solo los reenvíos declarados pueden repetir una identidad; se verifica
        # su contenido más adelante, sin descartarlos del stream.
        if not event['is_injected_duplicate']:
            if event['event_type'] == 'payment_attempt' and event['payment_status'] == 'succeeded':
                db.execute('INSERT INTO payments VALUES (?, ?)', (event['order_id'], event['event_time']))
            if event['event_type'] == 'purchase':
                if event['event_origin'] == 'synthetic':
                    paid = db.execute('SELECT success_time FROM payments WHERE order_id=?', (event['order_id'],)).fetchone()
                    if not paid or paid[0] > event['event_time']:
                        raise ValueError('Compra sintética sin pago exitoso previo')
                db.execute('INSERT INTO purchases VALUES (?, ?, ?, ?, ?, ?, 0)', (
                    event['event_id'], event['order_id'], event['product_id'], event['user_id'], event['event_time'], event['quantity']))
                db.execute('INSERT OR IGNORE INTO inventory(product_id) VALUES (?)', (event['product_id'],))
                stock = db.execute('SELECT stock FROM inventory WHERE product_id=?', (event['product_id'],)).fetchone()[0]
                # Reposición mínima inferida antes de cada compra. No representa
                # inventario observado ni se usa como detector de faltantes.
                supply = max(0, event['quantity'] - stock)
                db.execute('UPDATE inventory SET stock=stock+?-?, supplied=supplied+?, purchased=purchased+? WHERE product_id=?',
                           (supply, event['quantity'], supply, event['quantity'], event['product_id']))
            if event['event_type'] == 'return':
                purchase = db.execute('SELECT order_id, product_id, user_id, time, quantity, returned FROM purchases WHERE event_id=?',
                                      (event['original_purchase_event_id'],)).fetchone()
                if (not purchase or tuple(purchase[:3]) != (event['order_id'], event['product_id'], event['user_id'])
                        or purchase[3] > event['event_time'] or purchase[5] + event['quantity'] > purchase[4]):
                    raise ValueError('Devolución inconsistente')
                db.execute('UPDATE purchases SET returned=returned+? WHERE event_id=?', (event['quantity'], event['original_purchase_event_id']))
                db.execute('UPDATE inventory SET stock=stock+?, returned=returned+? WHERE product_id=?', (event['quantity'], event['quantity'], event['product_id']))
        db.execute('INSERT INTO events(event_id,time,payload) VALUES (?, ?, ?)',
                   (event['event_id'], event['event_time'], json.dumps(event, ensure_ascii=False, sort_keys=True)))
        self.count += 1
        self.types[event['event_type']] += 1
        self.origins[event['event_origin']] += 1
        self.quality.update(event['quality_flags'])


def envelope(run, event_id, time, kind, origin, user, session, product=None):
    return dict(event_id=event_id, schema_version='1.0', event_time=time,
                ingested_at=None, event_type=kind, event_origin=origin,
                source_row_id=None, generation_run_id=run, synthetic_fields=[],
                user_id=user, user_session=session, product_id=product,
                category_id=None, category_code=None, brand=None, price=None,
                order_id=None, quantity=None, delivery_type=None, scheduled_at=None,
                priority=0, priority_reason='normal', payment_attempt_id=None,
                payment_method_id=None, device_id=None, payment_status=None,
                query=None, rating=None, original_purchase_event_id=None,
                scenario_id=None, is_injected_duplicate=False, is_injected_anomaly=False,
                quality_flags=[])


def controlled_events(db, run, seed, start):
    """Tres órdenes completas, co-compra, fallos de pago y un reenvío."""
    products = db.execute('SELECT product_id, category_id, category_code, brand, last_observed_price FROM catalog ORDER BY product_id LIMIT 2').fetchall()
    if len(products) < 2:
        raise ValueError('Se requieren dos productos de origen para los escenarios')
    rng = random.Random(seed)
    events = []
    base = datetime.fromisoformat(start.replace('Z', '+00:00'))

    def make(kind, product, order, delivery, offset):
        event = envelope(run, 'syn:event:' + stable_id(run, len(events)),
                         utc((base + timedelta(seconds=offset)).isoformat()), kind,
                         'synthetic', 'syn:user:demo', 'syn:session:demo', product[0])
        event.update(category_id=product[1], category_code=product[2], brand=product[3], price=product[4],
                     order_id=order, delivery_type=delivery, scenario_id='controlled-stage0',
                     priority=10 if delivery == 'express' else 0,
                     priority_reason='express_delivery' if delivery == 'express' else 'normal')
        if delivery == 'scheduled':
            event['scheduled_at'] = utc((base + timedelta(days=3)).isoformat())
        events.append(event)
        return event

    offset = 1
    first_purchase = None
    for delivery in ('express', 'standard', 'scheduled'):
        order = 'syn:order:' + stable_id(run, delivery)
        scheduled = utc((base + timedelta(days=3)).isoformat()) if delivery == 'scheduled' else None
        db.execute('INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (order, 'syn:user:demo', 'syn:session:demo', delivery, scheduled, 'controlled', 'synthetic'))
        for attempt in range(3 if delivery == 'express' else 1):
            event = make('payment_attempt', products[0], order, delivery, offset)
            event.update(payment_attempt_id='syn:payment:' + stable_id(run, delivery, attempt),
                         payment_method_id='syn:method:demo', device_id='syn:device:demo',
                         payment_status='failed' if delivery == 'express' and attempt < 2 else 'succeeded')
            if event['payment_status'] == 'failed':
                event.update(is_injected_anomaly=True, priority=100, priority_reason='failed_payment')
            offset += 1
        for product in products if delivery == 'express' else products[:1]:
            event = make('purchase', product, order, delivery, offset)
            event['quantity'] = rng.randint(1, 3)
            if first_purchase is None:
                first_purchase = event
            offset += 1
    event = make('return', products[0], first_purchase['order_id'], 'express', offset)
    event.update(quantity=1, original_purchase_event_id=first_purchase['event_id'])
    offset += 1
    event = make('review', products[0], first_purchase['order_id'], 'express', offset)
    event.update(rating=4, original_purchase_event_id=first_purchase['event_id'])
    offset += 1
    event = make('search', products[0], None, 'standard', offset)
    event['query'] = products[0][2] or products[0][3] or 'producto'
    event['product_id'] = None
    # El duplicado mantiene todo el contenido de negocio y su event_id.
    duplicate = dict(first_purchase, is_injected_duplicate=True,
                     quality_flags=list(first_purchase['quality_flags']))
    events.append(duplicate)
    for event in events:
        event['synthetic_fields'] = [k for k, v in event.items()
                                     if v is not None and k not in {'synthetic_fields', 'is_injected_duplicate'}]
        if event['price'] == '0.00':
            event['quality_flags'].append('zero_price_review')
    return events


SCENARIO_SIZE = 13  # 5 pagos + 4 compras + devolución + reseña + búsqueda + reenvío


def fraud_events(db, run, start):
    """Ráfaga controlada, reenvío de pago y expiración seis minutos después."""
    product = db.execute('SELECT product_id FROM catalog ORDER BY product_id LIMIT 1').fetchone()[0]
    order = 'syn:order:fraud:' + stable_id(run)
    db.execute('INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)',
               (order, 'syn:user:fraud', 'syn:session:fraud', 'standard', None, 'controlled', 'synthetic'))
    base = datetime.fromisoformat(start.replace('Z', '+00:00')).replace(second=0, microsecond=0) + timedelta(minutes=1)
    events = []
    for index in range(25):
        offset = index if index < 24 else 360
        event = envelope(run, 'syn:event:fraud:' + stable_id(run, index),
                         utc((base + timedelta(seconds=offset)).isoformat()), 'payment_attempt',
                         'synthetic', 'syn:user:fraud', 'syn:session:fraud', product)
        event.update(order_id=order, payment_attempt_id=f'syn:attempt:{run}:{index}',
                     payment_method_id='syn:method:fraud', device_id='syn:device:burst',
                     payment_status='failed', scenario_id='controlled-stage6',
                     is_injected_anomaly=index < 24)
        event['synthetic_fields'] = [key for key, value in event.items()
                                     if value is not None and key != 'synthetic_fields']
        events.append(event)
    events.insert(24, dict(events[0], is_injected_duplicate=True))
    return events


def prepare(source, output, size, config, profile='stage0'):
    source, output = Path(source).resolve(), Path(output).resolve()
    if profile not in {'stage0', 'stage6'}:
        raise ValueError('Perfil desconocido')
    scenario_size = SCENARIO_SIZE if profile == 'stage0' else 39
    if size is not None and size < scenario_size + 2:
        raise ValueError(f'Tamaño mínimo: {scenario_size + 2}')
    if config['chunk_size'] <= 0 or config['order_window_minutes'] <= 0:
        raise ValueError('Bloque y ventana deben ser positivos')
    if output == source or source in output.parents:
        raise ValueError('La salida debe estar separada del CSV')
    output.mkdir(parents=True, exist_ok=False)
    source_hash = digest_file(source)
    run = stable_id(source_hash, size, json.dumps(config, sort_keys=True))
    if profile != 'stage0':
        run = stable_id(run, profile)
    db = connect(output / 'entities.sqlite')
    writer = Writer(db)
    source_count = 0
    selected_limit = None if size is None else size - scenario_size
    missing_sessions = 0
    candidates = 0
    conflicts = 0
    last_time = None
    boundary_session = None
    try:
        with source.open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != SOURCE_COLUMNS:
                raise ValueError('Cabecera distinta al esquema REES46')
            for row_id in count(1):
                if selected_limit is not None and source_count >= selected_limit:
                    break
                row = next(reader, None)
                if row is None:
                    if selected_limit is not None:
                        raise ValueError('Fuente insuficiente para el tamaño solicitado')
                    break
                source_count += 1
                if None in row or any(v is None for v in row.values()):
                    raise ValueError(f'Fila {row_id}: cantidad de columnas inválida')
                time = utc(row['event_time'])
                if last_time and time < last_time:
                    raise ValueError(f'Fila {row_id}: retroceso temporal')
                last_time = time
                session = row['user_session'] or f'syn:missing-session:{stable_id(source_hash, row_id)}'
                event = envelope(run, 'src:event:' + stable_id(source_hash, row_id), time,
                                 row['event_type'], 'real', row['user_id'], session, row['product_id'])
                event.update(source_row_id=row_id, category_id=row['category_id'],
                             category_code=row['category_code'] or None, brand=row['brand'] or None,
                             price=money(row['price']))
                # Mantener los valores observados evita imputación con datos futuros.
                if not row['brand']:
                    event['quality_flags'].append('unknown_brand')
                if not row['category_code']:
                    event['quality_flags'].append('unknown_category_code')
                if not row['user_session']:
                    missing_sessions += 1
                    event['synthetic_fields'].append('user_session')
                    event['quality_flags'].append('missing_session_isolated')
                if event['price'] == '0.00':
                    event['quality_flags'].append('zero_price_review')
                fingerprint = stable_id(*(row[k] for k in SOURCE_COLUMNS))
                match = db.execute('SELECT first_row FROM fingerprints WHERE fingerprint=?', (fingerprint,)).fetchone()
                if match:
                    candidates += 1
                    event['quality_flags'].append('possible_source_duplicate')
                    event['possible_duplicate_of_source_row'] = match[0]
                else:
                    db.execute('INSERT INTO fingerprints VALUES (?, ?)', (fingerprint, row_id))
                previous = db.execute('SELECT category_id,category_code,brand,last_observed_price FROM catalog WHERE product_id=?', (event['product_id'],)).fetchone()
                attrs = (event['category_id'], event['category_code'], event['brand'], event['price'])
                if previous and previous != attrs:
                    conflicts += 1
                    event['quality_flags'].append('catalog_observation_changed')
                db.execute('INSERT OR REPLACE INTO catalog VALUES (?, ?, ?, ?, ?, ?)', (event['product_id'], *attrs, time))
                if event['event_type'] == 'purchase':
                    epoch = int(datetime.fromisoformat(time.replace('Z', '+00:00')).timestamp())
                    bucket = epoch // (config['order_window_minutes'] * 60)
                    order = 'syn:order:' + stable_id(source_hash, event['user_id'], session, bucket)
                    event.update(order_id=order, quantity=1, delivery_type='standard')
                    event['synthetic_fields'] += ['order_id', 'quantity', 'delivery_type']
                    db.execute('INSERT OR IGNORE INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)',
                               (order, event['user_id'], session, 'standard', None, 'user_session_fixed_utc_window', 'derived_from_real'))
                writer.add(event)
                boundary_session = {'user_id': row['user_id'], 'user_session': session, 'source_row_id': row_id}
                if row_id % config['chunk_size'] == 0:
                    db.commit()
            # Nunca se supone que el prefijo cierre sesiones u órdenes.
            truncated = next(reader, None) is not None
        if not last_time:
            raise ValueError('Fuente vacía')
        scenarios = controlled_events(db, run, config['seed'], last_time)
        if profile == 'stage6':
            scenarios.extend(fraud_events(db, run, max(e['event_time'] for e in scenarios)))
        if len(scenarios) != scenario_size:
            raise AssertionError('Reserva de escenarios inconsistente')
        for event in scenarios:
            writer.add(event)
        db.execute('CREATE INDEX events_time ON events(time,seq)')
        db.execute('CREATE INDEX events_identity ON events(event_id)')
        db.commit()
        validations = validate_dataset(db)
        with (output / 'events.jsonl').open('w', encoding='utf-8') as stream:
            for (payload,) in db.execute('SELECT payload FROM events ORDER BY time,seq'):
                stream.write(payload + '\n')
        extra_artifacts = {}
        if profile == 'stage6':
            with (output / 'entidades.csv').open('w', newline='', encoding='utf-8') as stream:
                writer_csv = csv.writer(stream)
                writer_csv.writerow(['tipo', 'identificador', 'motivo'])
                writer_csv.writerows([['cuenta', 'syn:user:flagged', 'Caso sintético'],
                                     ['dispositivo', 'syn:device:demo', 'Caso sintético'],
                                     ['medio_pago', 'syn:method:flagged', 'Caso sintético']])
            extra_artifacts['entidades.csv'] = digest_file(output / 'entidades.csv')
        manifest = dict(schema_version='1.0', profile=profile, generation_run_id=run, seed=config['seed'], config=config,
                        source={'path': str(source), 'sha256': source_hash, 'rows_selected': source_count},
                        selection={'rule': 'chronological_prefix_plus_reserved_scenarios', 'requested_events': size,
                                   'reserved_scenario_events': scenario_size, 'prefix_may_cut_sessions_or_orders': truncated,
                                   'last_source_row': boundary_session, 'dependency_policy': 'real_groups_are_prefix_only;controlled_orders_complete'},
                        counts={'total': writer.count, 'by_type': dict(writer.types), 'by_origin': dict(writer.origins),
                                'synthetic_fraction': writer.origins['synthetic'] / writer.count,
                                'source_duplicate_candidates': candidates, 'missing_sessions_isolated': missing_sessions,
                                'catalog_changes': conflicts, 'quality_flags': dict(writer.quality)},
                        validation=validations, policies=POLICIES,
                        artifacts={'events.jsonl': digest_file(output / 'events.jsonl'),
                                   'entities.sqlite': digest_file(output / 'entities.sqlite'), **extra_artifacts},
                        environment={'python': platform.python_version(), 'platform': platform.platform()},
                        code_sha256=digest_file(__file__))
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
        return manifest
    finally:
        db.close()


def validate_dataset(db):
    dangling = 0
    duplicates = 0
    for event_id, count in db.execute('SELECT event_id,COUNT(*) FROM events GROUP BY event_id HAVING COUNT(*)>1'):
        base = None
        for (payload,) in db.execute('SELECT payload FROM events WHERE event_id=? ORDER BY seq', (event_id,)):
            event = json.loads(payload)
            duplicate = event.pop('is_injected_duplicate')
            if base is None:
                if duplicate:
                    raise ValueError('Reenvío sin original')
                base = event
            elif not duplicate or event != base:
                raise ValueError('Identidad repetida con contenido distinto')
            else:
                duplicates += 1
    for (payload,) in db.execute('SELECT payload FROM events ORDER BY time,seq'):
        event = json.loads(payload)
        validate(event)
        if event['order_id'] and not db.execute('SELECT 1 FROM orders WHERE order_id=?', (event['order_id'],)).fetchone():
            dangling += 1
        if event['product_id'] and not db.execute('SELECT 1 FROM catalog WHERE product_id=?', (event['product_id'],)).fetchone():
            dangling += 1
    invalid_stock = db.execute('SELECT COUNT(*) FROM inventory WHERE stock<0 OR stock!=supplied-purchased+returned').fetchone()[0]
    over_returned = db.execute('SELECT COUNT(*) FROM purchases WHERE returned>quantity').fetchone()[0]
    if dangling or invalid_stock or over_returned:
        raise ValueError('Integridad referencial o inventario inválido')
    return {'passed': True, 'dangling_references': dangling, 'invalid_inventory': invalid_stock,
            'over_returned_purchases': over_returned, 'verified_duplicate_resends': duplicates}


POLICIES = {
    'money': 'decimal strings, exactly 2 decimals; never float',
    'unknown_attributes': 'null; preserve category_id; do not impute',
    'zero_price': 'keep and flag zero_price_review',
    'missing_session': 'unique synthetic session per source row',
    'source_identity': 'SHA256(full source bytes hash, physical record number); equal rows retain distinct IDs',
    'catalog': 'last observation in selected prefix; conflicts flagged; not current market price',
    'inventory': 'synthetic zero initial stock; minimal inferred replenishment before each unique purchase; returns restore stock',
    'real_orders': 'synthetic user-session fixed UTC buckets; quantity=1; standard delivery; payments unknown',
    'controlled_orders': 'three complete orders; express with two distinct products; payment precedes purchase; return<=purchased',
    'priority': 'failed payment=100; express=10; normal=0; evaluation labels never consulted',
    'timestamps': 'event_time preserved in UTC; ingested_at assigned by replay',
    'evaluation': 'injected labels evaluate simulation only; no real fraud claims',
}
