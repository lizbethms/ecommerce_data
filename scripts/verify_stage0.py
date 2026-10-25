#!/usr/bin/env python3
"""Comprueba los artefactos preparados y las salidas reales de la FIFO."""
import argparse
from collections import Counter
from itertools import zip_longest
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.prepare import digest_file, validate_dataset
from src.data.schema import utc, validate


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(prepared_paths, metric_paths):
    datasets = []
    by_count = {}
    for prepared in prepared_paths:
        manifest = json.loads((prepared / 'manifest.json').read_text())
        for name, expected in manifest['artifacts'].items():
            require(digest_file(prepared / name) == expected, f'Hash incorrecto: {prepared / name}')
        with sqlite3.connect(prepared / 'entities.sqlite') as db:
            validations = validate_dataset(db)
        count = 0
        types = Counter()
        previous = ''
        with (prepared / 'events.jsonl').open() as stream:
            for line in stream:
                event = json.loads(line)
                validate(event)
                require(event['event_time'] >= previous, 'Retroceso temporal')
                previous = event['event_time']
                types[event['event_type']] += 1
                count += 1
        require(count == manifest['counts']['total'], 'Conteo distinto al manifiesto')
        require(dict(types) == manifest['counts']['by_type'], 'Composición distinta al manifiesto')
        by_count[count] = prepared / 'events.jsonl'
        datasets.append(dict(path=str(prepared), total=count, counts=manifest['counts'], validation=validations))
    replays = []
    for metrics_path in metric_paths:
        metrics = json.loads(metrics_path.read_text())
        source = by_count[metrics['consumed']]
        with source.open() as original, Path(metrics['output']).open() as emitted:
            count = 0
            for before, after in zip_longest(original, emitted):
                require(before is not None and after is not None, 'Pérdida o adición de eventos')
                before, after = json.loads(before), json.loads(after)
                received_at = after['event']['ingested_at']
                require(bool(received_at), 'Falta ingested_at')
                utc(received_at)
                after['event']['ingested_at'] = None
                require(before == after['event'], 'Contenido u orden FIFO alterado')
                require(before['event_id'] == after['event_id'], 'Identidad del sobre alterada')
                count += 1
        require(count == metrics['produced'] == metrics['consumed'], 'Conteos de reproducción inconsistentes')
        require(metrics['queue_peak'] <= metrics['queue_capacity'] and metrics['fifo_drained'], 'Capacidad o vaciado incorrectos')
        replays.append(dict(metrics_file=str(metrics_path), verified_events=count, **metrics))
    return {'passed': True, 'datasets': datasets, 'replays': replays,
            'scope': 'single verification runs; not statistical benchmarks; 100K/1M/10M not executed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, nargs='+', required=True)
    parser.add_argument('--metrics', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve() in {p.resolve() for p in args.metrics}:
        parser.error('El informe requiere un archivo nuevo')
    result = verify(args.prepared, args.metrics)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': True, 'datasets': len(result['datasets']), 'replays': len(result['replays'])}))
