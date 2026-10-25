"""Persistencia Parquet con tipos explícitos; la lectura devuelve el contrato textual.

En disco: fechas como timestamp UTC y dinero como decimal128(12,2), nunca float.
En memoria (al leer): fechas ISO con sufijo Z y precio con dos decimales, igual
que los eventos que valida ``schema.validate``.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

TIMESTAMP = pa.timestamp('us', tz='UTC')
MONEY = pa.decimal128(12, 2)
TEXTS = pa.list_(pa.string())

EVENT_SCHEMA = pa.schema([
    ('event_id', pa.string()), ('schema_version', pa.string()),
    ('event_time', TIMESTAMP), ('ingested_at', TIMESTAMP),
    ('event_type', pa.string()), ('event_origin', pa.string()),
    ('source_row_id', pa.int64()), ('generation_run_id', pa.string()),
    ('synthetic_fields', TEXTS),
    ('user_id', pa.string()), ('user_session', pa.string()), ('product_id', pa.string()),
    ('category_id', pa.string()), ('category_code', pa.string()), ('brand', pa.string()),
    ('price', MONEY),
    ('order_id', pa.string()), ('quantity', pa.int32()), ('delivery_type', pa.string()),
    ('scheduled_at', TIMESTAMP),
    ('priority', pa.int32()), ('priority_reason', pa.string()),
    ('payment_attempt_id', pa.string()), ('payment_method_id', pa.string()),
    ('device_id', pa.string()), ('payment_status', pa.string()),
    ('query', pa.string()), ('rating', pa.int32()), ('original_purchase_event_id', pa.string()),
    ('scenario_id', pa.string()), ('is_injected_duplicate', pa.bool_()),
    ('is_injected_anomaly', pa.bool_()), ('quality_flags', TEXTS),
    ('possible_duplicate_of_source_row', pa.int64()),
])

ENTITY_SCHEMAS = {
    'catalog': pa.schema([('product_id', pa.string()), ('category_id', pa.string()),
                          ('category_code', pa.string()), ('brand', pa.string()),
                          ('last_observed_price', MONEY), ('observed_at', TIMESTAMP)]),
    'orders': pa.schema([('order_id', pa.string()), ('user_id', pa.string()),
                         ('user_session', pa.string()), ('delivery_type', pa.string()),
                         ('scheduled_at', TIMESTAMP), ('grouping_rule', pa.string()),
                         ('origin', pa.string())]),
    'inventory': pa.schema([('product_id', pa.string()), ('stock', pa.int64()),
                            ('supplied', pa.int64()), ('purchased', pa.int64()),
                            ('returned', pa.int64())]),
    'purchases': pa.schema([('event_id', pa.string()), ('order_id', pa.string()),
                            ('product_id', pa.string()), ('user_id', pa.string()),
                            ('time', TIMESTAMP), ('quantity', pa.int64()), ('returned', pa.int64())]),
    'payments': pa.schema([('order_id', pa.string()), ('success_time', TIMESTAMP)]),
    'flags': pa.schema([('kind', pa.string()), ('value', pa.string()), ('reason', pa.string())]),
}


def _to_arrow(value, kind):
    if value is None:
        return None
    if kind == TIMESTAMP:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    if kind == MONEY:
        return Decimal(value)
    return value


def _from_arrow(value, kind):
    if value is None:
        return None
    if kind == TIMESTAMP:
        return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    if kind == MONEY:
        return format(value, '.2f')
    return value


def _batch(rows, schema):
    converted = [{f.name: _to_arrow(row.get(f.name), f.type) for f in schema} for row in rows]
    for row in converted:
        for f in schema:
            if f.type == TEXTS and row[f.name] is None:
                row[f.name] = []
    return pa.Table.from_pylist(converted, schema=schema)


def write_rows(rows, path, schema, batch_size=2048):
    """Escribe en bloques: la memoria depende de batch_size, no del total."""
    count = 0
    with pq.ParquetWriter(path, schema, compression='zstd') as writer:
        block = []
        for row in rows:
            block.append(row)
            if len(block) >= batch_size:
                writer.write_table(_batch(block, schema))
                count += len(block)
                block = []
        if block or not count:
            writer.write_table(_batch(block, schema))
            count += len(block)
    return count


def write_events(events, path, batch_size=2048):
    return write_rows(events, path, EVENT_SCHEMA, batch_size)


def write_entities(db, output, batch_size=2048):
    written = {}
    for table, schema in ENTITY_SCHEMAS.items():
        cursor = db.execute(f'SELECT {",".join(schema.names)} FROM {table} ORDER BY rowid')
        rows = (dict(zip(schema.names, values)) for values in cursor)
        written[f'{table}.parquet'] = write_rows(rows, output / f'{table}.parquet', schema, batch_size)
    return written


def iter_rows(path, batch_size=2048):
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    for batch in parquet.iter_batches(batch_size=batch_size):
        for row in batch.to_pylist():
            yield {f.name: _from_arrow(row[f.name], f.type) for f in schema}


def iter_events(path, batch_size=2048):
    """Eventos con el mismo contrato que events.jsonl (sin el campo opcional nulo)."""
    for event in iter_rows(path, batch_size):
        if event.get('possible_duplicate_of_source_row') is None:
            event.pop('possible_duplicate_of_source_row', None)
        yield event


def iter_event_blocks(path, size):
    block = []
    for event in iter_events(path, size):
        block.append(event)
        if len(block) >= size:
            yield block
            block = []
    if block:
        yield block
