"""Mide memoria aislada por estructura y escala; guarda evidencia incremental.

Ejemplo:
  python scripts/benchmark_memoria.py --datos data/prepared/perfil_1K data/prepared/perfil_10K \
    --salida results/experimentos/memoria_01 --repeticiones 3
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.memoria import CASOS, measure, save_evidence
from src.data.prepare import digest_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datos', type=Path, nargs='+', required=True,
                        help='Una o más carpetas preparadas con events.parquet')
    parser.add_argument('--salida', type=Path, help='Carpeta nueva para evidencia e informe')
    parser.add_argument('--repeticiones', type=int, default=3)
    parser.add_argument('--timeout', type=int, default=3600,
                        help='Segundos máximos por proceso; registra tiempos agotados')
    parser.add_argument('--casos', nargs='+', choices=CASOS, default=list(CASOS))
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--caso', choices=CASOS, help=argparse.SUPPRESS)
    parser.add_argument('--repeticion', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    paths = [directory.resolve() / 'events.parquet' for directory in args.datos]
    if any(not path.is_file() for path in paths):
        parser.error('Cada carpeta de --datos debe contener events.parquet')
    if args.repeticiones < 1:
        parser.error('--repeticiones debe ser positivo')
    if args.timeout < 1:
        parser.error('--timeout debe ser positivo')
    if args.worker:
        if len(paths) != 1 or args.caso is None or args.repeticion is None:
            parser.error('Worker requiere un archivo, --caso y --repeticion')
        print(json.dumps(measure(paths[0], args.caso, args.repeticion), ensure_ascii=False))
        return
    if args.salida is None:
        parser.error('--salida es obligatorio')
    output = args.salida.resolve()
    output.mkdir(parents=True, exist_ok=False)
    evidence_path = output / 'evidencia_memoria.json'
    sources = [dict(datos=str(path.parent), events_sha256=digest_file(path)) for path in paths]
    rows = []
    for path in paths:
        for case in args.casos:
            for repetition in range(1, args.repeticiones + 1):
                command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--datos',
                           str(path.parent), '--caso', case, '--repeticion', str(repetition)]
                print(f'{path.parent.name}: {case} {repetition}/{args.repeticiones}', flush=True)
                try:
                    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                         timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    rows.append(dict(escala=path.parent.name, caso=case, repeticion=repetition,
                                     estado='tiempo_agotado', detalle=f'Más de {args.timeout} s'))
                else:
                    if run.returncode:
                        rows.append(dict(escala=path.parent.name, caso=case, repeticion=repetition,
                                         estado='error', detalle=run.stderr[-2000:] or f'Código {run.returncode}'))
                    else:
                        rows.append(json.loads(run.stdout))
                save_evidence(evidence_path, rows, sources)
    from src.analysis.informe_memoria import export_memory_report
    export_memory_report(json.loads(evidence_path.read_text()), output)
    print(f'Informe: {output / "resumen_memoria.md"}')
    if any(row['estado'] != 'completado' for row in rows):
        raise SystemExit('Algunas mediciones fallaron; revisar evidencia_memoria.json')


if __name__ == '__main__':
    main()
