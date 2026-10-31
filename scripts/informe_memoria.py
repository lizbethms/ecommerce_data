"""Combina campañas de memoria y genera un informe único por escalas."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.informe_memoria import export_memory_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidencias', type=Path, nargs='+', required=True)
    parser.add_argument('--salida', type=Path, required=True, help='Carpeta nueva')
    args = parser.parse_args()
    rows, sources = [], {}
    for path in args.evidencias:
        data = json.loads(path.read_text(encoding='utf-8'))
        for source in data['fuentes']:
            old = sources.get(source['datos'])
            if old and old['events_sha256'] != source['events_sha256']:
                parser.error(f'Versiones distintas de {source["datos"]}')
            sources[source['datos']] = source
        rows.extend(data['filas'])
    identities = [(row['escala'], row['caso'], row['repeticion']) for row in rows]
    if len(identities) != len(set(identities)):
        parser.error('Las evidencias contienen mediciones repetidas del mismo caso')
    output = args.salida.resolve()
    output.mkdir(parents=True, exist_ok=False)
    combined = dict(version=1, fuentes=list(sources.values()), filas=rows,
                    alcance='Campañas de memoria combinadas; input excluido de tracemalloc')
    (output / 'evidencia_memoria.json').write_text(json.dumps(combined, ensure_ascii=False, indent=2) + '\n',
                                                   encoding='utf-8')
    export_memory_report(combined, output)
    print(f'Informe: {output / "resumen_memoria.md"}')


if __name__ == '__main__':
    main()
