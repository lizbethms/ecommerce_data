#!/usr/bin/env python3
"""CLI de preparación y reproducción; ejecutar desde cualquier directorio."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tracemalloc
import resource
import platform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.prepare import prepare
from src.pipeline.stage0 import run_stage0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/stage0.json')
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('prepare')
    build.add_argument('--source', type=Path, default=ROOT / '10M.csv')
    selection = build.add_mutually_exclusive_group(required=True)
    selection.add_argument('--size', type=int)
    selection.add_argument('--all-source', action='store_true', help='Conservar todas las filas y añadir escenarios')
    build.add_argument('--output', type=Path, required=True)
    replay = sub.add_parser('replay')
    replay.add_argument('--events', type=Path, required=True)
    replay.add_argument('--output', type=Path, required=True)
    replay.add_argument('--metrics', type=Path, required=True)
    replay.add_argument('--mode', choices=['constant', 'burst', 'historical', 'unlimited'], default='unlimited')
    replay.add_argument('--consumer-delay', type=float, default=0)
    replay.add_argument('--capacity', type=int)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.command == 'prepare':
        result = prepare(args.source, args.output, args.size, config)
        print(json.dumps({'output': str(args.output), 'counts': result['counts'], 'validation': result['validation']}, indent=2))
    else:
        if args.capacity is not None:
            config['queue_capacity'] = args.capacity
        if args.metrics.resolve() in {args.events.resolve(), args.output.resolve()} or args.metrics.exists():
            parser.error('Las métricas requieren un archivo nuevo separado de entrada y salida')
        tracemalloc.start()
        result = asyncio.run(run_stage0(args.events, args.output, config, args.mode, args.consumer_delay))
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result.update(python_memory_current_bytes=current, python_memory_peak_bytes=peak,
                      process_max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024),
                      python=platform.python_version(), platform=platform.platform(), config=config)
        args.metrics.parent.mkdir(parents=True, exist_ok=True)
        args.metrics.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
