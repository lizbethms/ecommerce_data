#!/usr/bin/env python3
"""Procesar eventos o sobres de etapa 0 con persistencia CSV."""
import argparse
import json
from pathlib import Path
import platform
import sys
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.pipeline.stage6 import run_stage6


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--history', required=True, type=Path)
    parser.add_argument('--entities', type=Path)
    parser.add_argument('--metrics', required=True, type=Path)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/stage6.json')
    args = parser.parse_args()
    occupied = [args.events, args.output, args.history, args.config]
    if args.entities:
        occupied.append(args.entities)
    if args.metrics.exists() or args.metrics.resolve() in {p.resolve() for p in occupied}:
        parser.error('Las métricas requieren un archivo nuevo y separado')
    config = json.loads(args.config.read_text())
    tracemalloc.start()
    metrics = run_stage6(args.events, args.output, args.history, config, args.entities)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    metrics.update(memoria_python_actual_bytes=current, memoria_python_pico_bytes=peak,
                   python=platform.python_version(), plataforma=platform.platform())
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
