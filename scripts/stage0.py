#!/usr/bin/env python3
"""CLI de muestreo, preparación y reproducción; ejecutar desde cualquier directorio."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tracemalloc
import platform

try:
    import resource
except ImportError:  # Windows
    resource = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.prepare import digest_file, prepare
from src.data.sample import sample_sessions, write_manifest
from src.pipeline.stage0 import run_stage0


def max_rss_bytes():
    if resource is not None:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]

    counters = Counters(cb=ctypes.sizeof(Counters))
    kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return None
    return counters.PeakWorkingSetSize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/stage0.json')
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('prepare')
    build.add_argument('--source', type=Path, default=ROOT / 'data/10M.csv')
    selection = build.add_mutually_exclusive_group(required=True)
    selection.add_argument('--size', type=int)
    selection.add_argument('--all-source', action='store_true', help='Conservar todas las filas y añadir escenarios')
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--format', choices=['jsonl', 'parquet'], default='jsonl')
    sample = sub.add_parser('sample', help='Copia pequeña por sesiones + preparación Parquet')
    sample.add_argument('--source', type=Path, default=ROOT / 'data/10M.csv')
    sample.add_argument('--rows', type=int, help='Filas objetivo de la copia (por defecto, config sample.target_rows)')
    sample.add_argument('--csv-output', type=Path, help='Copia CSV (por defecto data/sample_<N>.csv)')
    sample.add_argument('--output', type=Path, required=True)
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
        result = prepare(args.source, args.output, args.size, config, args.format)
        print(json.dumps({'output': str(args.output), 'counts': result['counts'], 'validation': result['validation']}, indent=2))
    elif args.command == 'sample':
        sampling, synthetic = config.pop('sample'), config.pop('synthetic', None)
        rows = args.rows or sampling['target_rows']
        label = f'{rows // 1000}K' if rows % 1000 == 0 else str(rows)
        csv_output = args.csv_output or ROOT / f'data/sample_{label}.csv'
        info = sample_sessions(args.source, csv_output, rows, sampling['window_rows'], config['seed'],
                               sampling['max_session_rows'], sampling['purchase_share'], sampling['guard_minutes'])
        info = write_manifest(info, csv_output.with_name(csv_output.stem + '_manifest.json'), digest_file(args.source))
        result = prepare(csv_output, args.output, None, config, 'parquet', synthetic)
        print(json.dumps({'sample': {k: info[k] for k in ('output', 'rows_written', 'by_type', 'sessions_chosen')},
                          'output': str(args.output), 'counts': result['counts'],
                          'synthetic': result['selection']['synthetic_summary'],
                          'validation': result['validation']}, indent=2))
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
                      process_max_rss_bytes=max_rss_bytes(),
                      python=platform.python_version(), platform=platform.platform(), config=config)
        args.metrics.parent.mkdir(parents=True, exist_ok=True)
        args.metrics.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
