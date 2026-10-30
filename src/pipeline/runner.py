"""Pipeline de ingesta: productor -> FIFO -> salida para el futuro preprocesamiento."""
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.replay import ReplayClock
from src.structures.fifo import BoundedFIFO


def read_block(stream, size):
    block = []
    for _ in range(size):
        line = stream.readline()
        if not line:
            break
        block.append(json.loads(line))
    return block


def event_blocks(path, size):
    """Bloques de eventos desde events.jsonl o events.parquet, con el mismo contrato."""
    if path.suffix == '.parquet':
        from src.data.parquet_io import iter_event_blocks
        yield from iter_event_blocks(path, size)
        return
    with path.open(encoding='utf-8') as stream:
        while block := read_block(stream, size):
            yield block


def write_block(stream, records):
    stream.writelines(json.dumps(record, ensure_ascii=False) + '\n' for record in records)


async def run_pipeline(events_path, output_path, config, mode='unlimited', consumer_delay=0):
    events_path, output_path = Path(events_path).resolve(), Path(output_path).resolve()
    if consumer_delay < 0 or config['chunk_size'] <= 0:
        raise ValueError('Retardo no negativo y bloque positivo requeridos')
    if events_path == output_path:
        raise ValueError('La salida no puede sobrescribir la entrada')
    fifo = BoundedFIFO(config['queue_capacity'])
    clock = ReplayClock(mode, config['rate'], config['burst_size'], config['burst_interval'], config['historical_speed'])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stats = dict(pipeline='ingestion', mode=mode, produced=0, consumed=0, queue_capacity=fifo.maxsize,
                 producer_wait_seconds=0.0, latency_seconds_sum=0.0, latency_seconds_max=0.0,
                 chunk_size=config['chunk_size'], consumer_delay=consumer_delay)
    sentinel = object()
    started = time.perf_counter()

    async def produce():
        blocks = event_blocks(events_path, config['chunk_size'])
        while block := await asyncio.to_thread(next, blocks, None):
            for event in block:
                await clock.wait(stats['produced'], event['event_time'])
                event = dict(event, ingested_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
                admitted = time.perf_counter()
                await fifo.put((event, admitted))
                stats['producer_wait_seconds'] += time.perf_counter() - admitted
                stats['produced'] += 1
        await fifo.put(sentinel)

    async def consume():
        with output_path.open('x', encoding='utf-8') as stream:
            output_block = []
            while True:
                item = await fifo.get()
                try:
                    if item is sentinel:
                        if output_block:
                            await asyncio.to_thread(write_block, stream, output_block)
                        break
                    event, admitted = item
                    if consumer_delay:
                        await asyncio.sleep(consumer_delay)
                    latency = time.perf_counter() - admitted
                    stats['latency_seconds_sum'] += latency
                    stats['latency_seconds_max'] = max(stats['latency_seconds_max'], latency)
                    output_block.append(dict(event_id=event['event_id'], event=event,
                                             entity_refs={k: event.get(k) for k in ('user_id', 'product_id', 'order_id')},
                                             stage_results={'ingestion': {'status': 'emitted', 'fifo_latency_seconds': latency}},
                                             processing_times={'ingestion': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}))
                    stats['consumed'] += 1
                    if len(output_block) >= config['chunk_size']:
                        await asyncio.to_thread(write_block, stream, output_block)
                        output_block = []
                finally:
                    fifo.task_done()

    async with asyncio.TaskGroup() as group:
        group.create_task(produce())
        group.create_task(consume())
    elapsed = time.perf_counter() - started
    stats.update(elapsed_seconds=elapsed, throughput_events_per_second=stats['consumed'] / elapsed,
                 queue_peak=fifo.peak_size, blocked_puts=fifo.blocked_puts,
                 latency_seconds_mean=stats['latency_seconds_sum'] / max(1, stats['consumed']),
                 fifo_drained=fifo.empty(), output=str(output_path))
    # Estas métricas excluyen preparación y miden lectura + pacing + buffer + sumidero.
    return stats
