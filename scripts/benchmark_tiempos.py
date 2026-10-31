"""Mide tiempos de construcción y de operación por estructura y escala; guarda evidencia incremental.

Ejemplo:
  python scripts/benchmark_tiempos.py --datos data/prepared/perfil_1K data/prepared/perfil_10K \
    --salida results/experimentos/tiempos_01
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.tiempos import CASOS, measure, save_evidence
from src.analysis.plataforma import plataforma
from src.data.prepare import digest_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datos', type=Path, nargs='+', required=True,
                        help='Una o más carpetas preparadas con events.parquet')
    parser.add_argument('--salida', type=Path, help='Carpeta nueva para evidencia e informe')
    parser.add_argument('--repeticiones', type=int, default=100,
                        help='Repeticiones del lote de operaciones de cada estructura')
    parser.add_argument('--repeticiones-construccion', type=int, default=3,
                        help='Construcciones completas por caso; son la operación cara en 1M y 10M')
    parser.add_argument('--semilla', type=int, default=2026)
    parser.add_argument('--timeout', type=int, default=3600,
                        help='Segundos máximos por proceso; registra tiempos agotados')
    parser.add_argument('--casos', nargs='+', choices=list(CASOS), default=list(CASOS))
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--caso', choices=list(CASOS), help=argparse.SUPPRESS)
    args = parser.parse_args()
    paths = [directory.resolve() / 'events.parquet' for directory in args.datos]
    if any(not path.is_file() for path in paths):
        parser.error('Cada carpeta de --datos debe contener events.parquet')
    if min(args.repeticiones, args.repeticiones_construccion, args.timeout) < 1:
        parser.error('Repeticiones y timeout deben ser positivos')
    if args.worker:
        if len(paths) != 1 or args.caso is None:
            parser.error('Worker requiere un archivo y --caso')
        row = measure(paths[0], args.caso, args.repeticiones_construccion, args.repeticiones, args.semilla)
        print(json.dumps(row))  # ASCII: la consola de Windows (cp1252) no codifica símbolos como Σ
        return
    if args.salida is None:
        parser.error('--salida es obligatorio')
    output = args.salida.resolve()
    output.mkdir(parents=True, exist_ok=False)
    evidence_path = output / 'evidencia_tiempos.json'
    sources = [dict(datos=str(path.parent), events_sha256=digest_file(path)) for path in paths]
    parameters = dict(repeticiones_operacion=args.repeticiones, repeticiones_construccion=args.repeticiones_construccion,
                      semilla=args.semilla, timeout_seg=args.timeout, plataforma=plataforma())
    rows = []
    for path in paths:
        for case in args.casos:
            command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--datos', str(path.parent),
                       '--caso', case, '--repeticiones', str(args.repeticiones),
                       '--repeticiones-construccion', str(args.repeticiones_construccion), '--semilla', str(args.semilla)]
            print(f'{path.parent.name}: {case}', flush=True)
            try:
                run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                                     timeout=args.timeout)
            except subprocess.TimeoutExpired:
                rows.append(dict(escala=path.parent.name, caso=case, estado='tiempo_agotado',
                                 detalle=f'Más de {args.timeout} s'))
            else:
                if run.returncode:
                    rows.append(dict(escala=path.parent.name, caso=case, estado='error',
                                     detalle=run.stderr[-2000:] or f'Código {run.returncode}'))
                else:
                    rows.append(json.loads(run.stdout.strip().splitlines()[-1]))
            save_evidence(evidence_path, rows, sources, parameters)
    from src.analysis.informe_tiempos import export_time_report
    export_time_report(json.loads(evidence_path.read_text(encoding='utf-8')), output)
    print(f'Informe: {output / "resumen_tiempos.md"}')
    if any(row['estado'] != 'completado' for row in rows):
        raise SystemExit('Algunas mediciones fallaron; revisar evidencia_tiempos.json')


if __name__ == '__main__':
    main()
