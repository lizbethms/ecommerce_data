"""Tablas y gráficos de memoria desde evidencia de procesos aislados."""
import csv
from pathlib import Path

import pandas as pd

from src.analysis.informe import markdown_table
from src.analysis.memoria import PARES, summary_rows
import matplotlib.pyplot as plt


LABELS = {'bloom': 'Bloom', 'set_exacto': 'set exacto',
          'cms': 'CMS', 'counter_exacto': 'Counter exacto',
          'cms_ventanas': 'CMS por ventanas', 'counter_ventanas': 'Counter por ventanas',
          'hnsw': 'HNSW', 'kd_tree': 'KD-Tree',
          'fuerza_bruta_vectores': 'Fuerza bruta vectorial',
          'minhash_lsh': 'MinHash/LSH', 'jaccard_exhaustivo': 'Jaccard exhaustivo'}
MIB = 1024 * 1024


def memory_section(evidence, output):
    """Devuelve Markdown e imágenes; no repite ninguna medición."""
    output = Path(output)
    figures = output / 'figuras'
    figures.mkdir(parents=True, exist_ok=True)
    rows = summary_rows(evidence['filas'])
    if not rows:
        return '## Memoria por estructura\n\n_Sin mediciones completadas._'
    completed = [row for row in evidence['filas'] if row['estado'] == 'completado']
    by_case = {(row['eventos_archivo'], row['caso']): row['workload_sha256'] for row in completed}
    for approx, exact in PARES:
        for size in {row['eventos_archivo'] for row in completed}:
            left, right = by_case.get((size, approx)), by_case.get((size, exact))
            if left and right and left != right:
                raise ValueError(f'Entradas distintas en {size}: {approx} frente a {exact}')
    platforms = sorted({row['plataforma'] for row in completed})
    seeds = sorted({str(row.get('semilla_datos')) for row in completed})
    compact = []
    for row in rows:
        compact.append(dict(escala=row['escala'], eventos=row['eventos_archivo'],
                            unidad=row['unidad'], n_indice=row['n_indice'],
                            estructura=LABELS[row['caso']],
                            n=row['repeticiones'],
                            actual_MiB=round(row['actual_indice_bytes_media'] / MIB, 4),
                            desv_actual_MiB=(round(row['actual_indice_bytes_desviacion'] / MIB, 4)
                                             if row['actual_indice_bytes_desviacion'] is not None else None),
                            pico_construccion_MiB=round(row['pico_construccion_bytes_media'] / MIB, 4),
                            desv_pico_construccion_MiB=(round(row['pico_construccion_bytes_desviacion'] / MIB, 4)
                                                        if row['pico_construccion_bytes_desviacion'] is not None else None),
                            pico_consulta_adicional_MiB=round(row['pico_adicional_consulta_bytes_media'] / MIB, 4),
                            pico_RSS_proceso_MiB=(round(row['pico_rss_proceso_bytes_media'] / MIB, 2)
                                                   if row['pico_rss_proceso_bytes_media'] is not None else None)))
    parts = ['## Memoria por estructura y escala',
             f'Plataforma: {", ".join(platforms)}. Semilla de preparación: {", ".join(seeds)}. '
             'La desviación estándar es muestral; con una repetición se indica como no estimable.',
             'Cada fila resume procesos nuevos e independientes. `actual` es la memoria Python incremental '
             'retenida por el índice después de construirlo; `pico_construccion` incluye sus temporales. '
             '`pico_consulta_adicional` se mide con el índice residente. El pico RSS corresponde al proceso '
             'completo, incluida la carga del archivo, y no debe restarse como si fuera solo el índice. '
             'Bloom y `set` reciben claves únicas; CMS y `Counter` reciben todas las actualizaciones de pago. '
             'Estas cargas incluyen los reenvíos del archivo, mientras que el panel de actividad cuenta solo '
             'eventos aceptados. '
             'La variante por ventanas usa seis bloques de 100 segundos para ambos métodos. '
             'Los vectores de 19 dimensiones se derivan del catálogo sin popularidad dinámica y son compartidos '
             'por HNSW, KD-Tree y fuerza bruta. Los conjuntos de usuarios se forman con vistas, carritos y '
             'compras del archivo y se comparten entre MinHash/LSH y Jaccard exhaustivo. Las referencias exactas '
             'de similitud conservan un mapa de entrada para consultas; su memoria no incluye los vectores o '
             'conjuntos de entrada, que se excluyen por igual de todos los índices.',
             'En la variante por ventanas, la memoria residente refleja los bloques activos al finalizar '
             'el archivo; el pico de construcción registra el máximo transitorio. Por eso una escala mayor '
             'puede terminar con menos memoria residente si su último tramo contiene menos bloques activos.',
             markdown_table(pd.DataFrame(compact))]
    measured = {row['eventos_archivo'] for row in rows}
    missing = [f'{size:,}' for size in (1000, 10000, 100000, 1000000, 10000000)
               if size not in measured]
    if missing:
        parts.append('Escalas aún sin medición en esta campaña: ' + ', '.join(missing) + ' eventos.')
    for pair_index, (approx, exact) in enumerate(PARES, 1):
        selected = [row for row in rows if row['caso'] in (approx, exact)]
        if not selected:
            continue
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        for ax, (field, title) in zip(axes, [('actual_indice_bytes_media', 'Memoria residente del índice'),
                                             ('pico_construccion_bytes_media', 'Pico de construcción')]):
            for case in (approx, exact):
                case_rows = sorted((row for row in selected if row['caso'] == case),
                                   key=lambda row: row['eventos_archivo'])
                if not case_rows:
                    continue
                xs = [row['n_indice'] for row in case_rows]
                ys = [row[field] / MIB for row in case_rows]
                ax.plot(xs, ys, 'o-', label=LABELS[case])
                for x, y, row in zip(xs, ys, case_rows):
                    ax.annotate(row['escala'], (x, y), xytext=(3, 5), textcoords='offset points', fontsize=8)
            if len({row['eventos_archivo'] for row in selected}) > 1:
                ax.set_xscale('log')
                ax.set_yscale('log')
            ax.margins(x=.16, y=.18)
            xlabel = ('Claves únicas' if approx == 'bloom' else
                      'Actualizaciones de pago' if approx in ('cms', 'cms_ventanas') else
                      'Vectores' if approx == 'hnsw' else 'Conjuntos')
            ax.set(xlabel=xlabel,
                   ylabel='MiB', title=title)
            ax.grid(alpha=.2)
            ax.legend()
        fig.tight_layout()
        name = f'memoria_{pair_index:02d}_{approx}'
        for suffix in ('png', 'svg', 'pdf'):
            fig.savefig(figures / f'{name}.{suffix}', dpi=180, bbox_inches='tight')
        plt.close(fig)
        parts.extend([f'### {LABELS[approx]} frente a {LABELS[exact]}',
                      f'![{name}](figuras/{name}.png)',
                      'Cada punto indica una escala del archivo; el eje horizontal usa el trabajo real de la '
                      'estructura. Con dos o más escalas ambos ejes son logarítmicos. Estos gráficos muestran '
                      'memoria observada; no prueban por sí solos una cota de complejidad.'])
    failures = [row for row in evidence['filas'] if row['estado'] != 'completado']
    if failures:
        parts.extend(['### Mediciones no completadas',
                      markdown_table(pd.DataFrame([{k: row.get(k) for k in
                                                    ('escala', 'caso', 'repeticion', 'estado', 'detalle')}
                                                   for row in failures]))])
    return '\n\n'.join(parts)


def export_memory_report(evidence, output):
    output = Path(output)
    rows = summary_rows(evidence['filas'])
    if rows:
        with (output / 'resumen_memoria.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    report = '# Experimento de memoria\n\n' + memory_section(evidence, output) + '\n'
    (output / 'resumen_memoria.md').write_text(report, encoding='utf-8')
    return rows
