#!/usr/bin/env python3
"""Verifica 1K/10K preparados, sobres, señales y recuperación CSV."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.prepare import digest_file
from src.pipeline.stage6 import run_stage6
from src.service.fraud import FraudService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-root', type=Path, default=ROOT / 'data/prepared')
    parser.add_argument('--results', type=Path, default=ROOT / 'results')
    parser.add_argument('--history-root', type=Path, default=ROOT / 'data/fraude/verificacion')
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    summary_path = args.results / 'stage6_verification_metrics.json'
    if summary_path.exists():
        parser.error('La verificación requiere una carpeta de resultados nueva')
    summary = {}
    for label, size in [('1K', 1000), ('10K', 10000)]:
        prepared = args.prepared_root / f'fraude_{label}'
        manifest = json.loads((prepared / 'manifest.json').read_text())
        assert manifest['counts']['total'] == size
        assert manifest['selection']['reserved_scenario_events'] == 39
        for name, checksum in manifest['artifacts'].items():
            assert digest_file(prepared / name) == checksum, name
        output = args.results / f'stage6_{label}.jsonl'
        history = args.history_root / f'{label}.csv'
        if history.exists():
            parser.error(f'Historial existente: {history}')
        metrics = run_stage6(prepared / 'events.jsonl', output, history, entities_path=prepared / 'entidades.csv')
        records = [json.loads(line) for line in output.read_text().splitlines()]
        assert len(records) == size
        counts = metrics['contadores']
        assert counts['duplicates'] == 2
        assert counts['payment_updates'] == 30
        assert counts['reviews'] == 10
        confirmed = [r for r in records if r['stage_results']['6']['risk_signals']['frequency']
                     and r['stage_results']['6']['risk_signals']['frequency']['verified']]
        assert len(confirmed) == 5
        assert records[-1]['stage_results']['6']['risk_signals']['frequency']['estimate'] == 1
        service = FraudService(history)
        try:
            restored = service.metrics()
            for key in restored:
                assert restored[key] == metrics[key], key
            replay = service.process(records[-1]['event'])
            assert replay['status'] == 'duplicate'
            assert service.windows.counts('syn:device:burst') == (1, 1)
        finally:
            service.close()
        metrics.update(recuperacion_verificada=True, total_verificado=size,
                       manifiesto_sha256=digest_file(prepared / 'manifest.json'),
                       datos_sha256=manifest['artifacts']['events.jsonl'],
                       salida_sha256=digest_file(output))
        (args.results / f'stage6_{label}_metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
        summary[label] = metrics
    summary_path.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'verificado': list(summary), 'salida': str(summary_path)}))


if __name__ == '__main__':
    main()
