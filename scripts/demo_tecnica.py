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
    parser.add_argument('--k', type=int, default=5)
    parser.add_argument('--consultas', type=int, default=5)
    parser.add_argument('--repeticiones', type=int, default=5)
    parser.add_argument('--evidencia', type=Path, help='JSON existente; solo regenera tablas y figuras junto a él')
    args = parser.parse_args()
    from src.analysis.informe import export_report
    if args.evidencia:
        if args.salida:
            parser.error('--evidencia regenera en su propia carpeta; no combinar con --salida')
        evidence = json.loads(args.evidencia.read_text(encoding='utf-8'))
        output = args.evidencia.parent
    else:
        evidence = collect_demo(args.datos, args.semilla, args.k, args.consultas, args.repeticiones)
        output = args.salida or ROOT / 'results/demo_tecnica' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        save_evidence(evidence, output)
    export_report(evidence, output)
    print(f'Evidencia, tablas y figuras: {output.resolve()}')
    print(json.dumps(evidence['grafo']['resumen'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
