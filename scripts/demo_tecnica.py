"""Genera evidencia de la demo o vuelve a renderizar una corrida sin repetir consultas."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.tecnica import collect_demo, save_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datos', type=Path, default=ROOT / 'data/prepared_5K')
    parser.add_argument('--salida', type=Path)
    parser.add_argument('--semilla', type=int, default=2026)
    parser.add_argument('--k', type=int, default=10)
    parser.add_argument('--consultas', type=int, default=10)
    parser.add_argument('--repeticiones', type=int, default=100)
    parser.add_argument('--evidencia', type=Path, help='JSON existente; solo regenera tablas y figuras junto a él')
    parser.add_argument('--memoria', type=Path, help='Evidencia de benchmark_memoria.py para añadir comparación de escalas')
    args = parser.parse_args()
    from src.analysis.informe import export_report
    memory_evidence = json.loads(args.memoria.read_text(encoding='utf-8')) if args.memoria else None
    if args.evidencia:
        if args.salida:
            parser.error('--evidencia regenera en su propia carpeta; no combinar con --salida')
        evidence = json.loads(args.evidencia.read_text(encoding='utf-8'))
        output = args.evidencia.parent
    else:
        evidence = collect_demo(args.datos, args.semilla, args.k, args.consultas, args.repeticiones)
        output = args.salida or ROOT / 'results/demo_tecnica' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    if memory_evidence is not None:
        data_path = Path(evidence['metadata']['datos']).resolve()
        matching = [source for source in memory_evidence.get('fuentes', [])
                    if Path(source['datos']).resolve() == data_path]
        if not matching or matching[0]['events_sha256'] != evidence['metadata']['archivos_sha256']['events.parquet']:
            parser.error('--memoria debe incluir la misma versión de events.parquet del informe')
    if not args.evidencia:
        save_evidence(evidence, output)
    export_report(evidence, output, memory_evidence)
    print(f'Evidencia, tablas y figuras: {output.resolve()}')
    print(json.dumps(evidence['grafo']['resumen'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
