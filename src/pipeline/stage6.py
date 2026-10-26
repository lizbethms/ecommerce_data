"""Adaptador por lotes; preserva los resultados de las etapas anteriores."""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from src.service.fraud import FraudService


def load_entities(service, path):
    with open(path, newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            service.change_entity(row['tipo'], row['identificador'], row['motivo'])


def run_stage6(events_path, output_path, history_path, config=None, entities_path=None):
    inputs = [Path(events_path).resolve()]
    if entities_path:
        inputs.append(Path(entities_path).resolve())
    output, history = Path(output_path).resolve(), Path(history_path).resolve()
    if output in inputs or history in inputs or output == history:
        raise ValueError('Entrada, salida e historial deben ser archivos separados')
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    service = FraudService(history, config)
    count = 0
    event_seconds = 0.0
    try:
        if entities_path:
            load_entities(service, entities_path)
        with open(events_path, encoding='utf-8') as source, output.open('x', encoding='utf-8') as target:
            for line in source:
                record = json.loads(line)
                event = record['event'] if 'event' in record else record
                envelope = record if 'event' in record else dict(event_id=event['event_id'], event=event,
                    entity_refs={key: event.get(key) for key in ('user_id', 'product_id', 'order_id')})
                event_started = time.perf_counter()
                envelope.setdefault('stage_results', {})['6'] = service.process(event)
                event_seconds += time.perf_counter() - event_started
                envelope.setdefault('processing_times', {})['6'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                target.write(json.dumps(envelope, ensure_ascii=False) + '\n')
                count += 1
        metrics = service.metrics()
        elapsed = time.perf_counter() - started
        metrics.update(eventos_procesados=count, duracion_segundos=elapsed,
                       eventos_por_segundo=count / elapsed, incluye_persistencia=True,
                       duracion_procesamiento_eventos_segundos=event_seconds,
                       duracion_escrituras_csv_segundos=service.history.write_seconds)
        return metrics
    finally:
        service.close()
