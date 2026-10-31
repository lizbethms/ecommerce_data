"""Tablas, pendientes log-log y figuras de la campaña de tiempos (scripts/benchmark_tiempos.py)."""
import math
import os
from pathlib import Path
import tempfile

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'ecommerce-demo-matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

from src.analysis.informe import markdown_table
from src.analysis.tiempos import PARES

GRUPOS = {
    'Estructuras base': ('fifo', 'merge_sort', 'hash_table', 'heap', 'lru', 'sparse_matrix', 'bplus_tree', 'trie',
                         'top_k', 'grafo'),
    'Probabilísticas y exactas': ('bloom', 'set_exacto', 'cms', 'counter_exacto', 'cms_ventanas', 'counter_ventanas'),
    'Similitud': ('kd_tree', 'hnsw', 'minhash_lsh'),
}


def pendiente(xs, ys):
    """Mínimos cuadrados de log10(y) frente a log10(x): exponente observado y R²."""
    puntos = [(math.log10(x), math.log10(y)) for x, y in zip(xs, ys) if x and y and x > 0 and y > 0]
    if len({x for x, _ in puntos}) < 2:
        return None, None
    mx = sum(x for x, _ in puntos) / len(puntos)
    my = sum(y for _, y in puntos) / len(puntos)
    sxx = sum((x - mx) ** 2 for x, _ in puntos)
    b = sum((x - mx) * (y - my) for x, y in puntos) / sxx
    total = sum((y - my) ** 2 for _, y in puntos)
    residual = sum((y - (my + b * (x - mx))) ** 2 for x, y in puntos)
    return b, (1 - residual / total) if total else 1.0


def _tabla(rows):
    filas = []
    for r in rows:
        c, o = r['construccion_ms'], r['operacion_ms']
        filas.append(dict(escala=r['escala'], eventos_archivo=r['eventos_archivo'], caso=r['caso'], n=r['n'],
                          unidad=r['unidad'], construccion_ms_media=c['media'], construccion_ms_desv=c['desviacion'],
                          construcciones=c['repeticiones'],
                          operacion_us_media=o['media'] * 1000 if o['media'] is not None else None,
                          operacion_us_desv=o['desviacion'] * 1000 if o['desviacion'] is not None else None,
                          repeticiones_operacion=o['repeticiones'], operaciones_por_repeticion=r['operaciones_por_repeticion'],
                          complejidad_construccion=r['complejidad_construccion'],
                          complejidad_operacion=r['complejidad_operacion']))
    return pd.DataFrame(filas).sort_values(['caso', 'n']) if filas else pd.DataFrame()


def _pendientes(rows, tabla):
    salida = []
    for caso, grupo in tabla.groupby('caso', sort=False):
        spec = next(r for r in rows if r['caso'] == caso)
        b_c, r2_c = pendiente(grupo['n'], grupo['construccion_ms_media'])
        b_o, r2_o = pendiente(grupo['n'], grupo['operacion_us_media'])
        salida.append(dict(caso=caso, escalas=len(grupo), n_min=grupo['n'].min(), n_max=grupo['n'].max(),
                           complejidad_construccion=spec['complejidad_construccion'],
                           pendiente_esperada_construccion=spec['pendiente_esperada_construccion'] if b_c is not None else None,
                           pendiente_observada_construccion=b_c, r2_construccion=r2_c,
                           complejidad_operacion=spec['complejidad_operacion'],
                           pendiente_esperada_operacion=spec['pendiente_esperada_operacion'] if b_o is not None else None,
                           pendiente_observada_operacion=b_o, r2_operacion=r2_o))
    return pd.DataFrame(salida)


def _comparacion(tabla):
    filas = []
    for aproximada, exacta in PARES:
        for escala in tabla['escala'].unique():
            a = tabla[(tabla['caso'] == aproximada) & (tabla['escala'] == escala)]
            e = tabla[(tabla['caso'] == exacta) & (tabla['escala'] == escala)]
            if a.empty or e.empty:
                continue
            a, e = a.iloc[0], e.iloc[0]
            filas.append(dict(escala=escala, n=a['n'], aproximada=aproximada, exacta=exacta,
                              construccion_ms_aproximada=a['construccion_ms_media'],
                              construccion_ms_exacta=e['construccion_ms_media'],
                              operacion_us_aproximada=a['operacion_us_media'], operacion_us_exacta=e['operacion_us_media'],
                              razon_operacion=a['operacion_us_media'] / e['operacion_us_media']
                              if e['operacion_us_media'] else None))
    return pd.DataFrame(filas)


def _calidad(rows, caso):
    return pd.DataFrame([dict(escala=r['escala'], n=r['n'], **r['calidad'])
                         for r in rows if r['caso'] == caso and r.get('calidad')]).sort_values('n') \
        if any(r['caso'] == caso and r.get('calidad') for r in rows) else pd.DataFrame()


def export_time_report(evidence, output):
    output = Path(output)
    tables_dir, figures_dir = output / 'tablas', output / 'figuras'
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    rows = [r for r in evidence['filas'] if r['estado'] == 'completado']
    fallidas = [r for r in evidence['filas'] if r['estado'] != 'completado']
    tabla = _tabla(rows)
    tables = {
        'tiempos_resumen': tabla,
        'tiempos_pendientes': _pendientes(rows, tabla) if not tabla.empty else pd.DataFrame(),
        'probabilisticas_vs_exactas': _comparacion(tabla) if not tabla.empty else pd.DataFrame(),
        'calidad_bloom': _calidad(rows, 'bloom'),
        'calidad_cms': _calidad(rows, 'cms'),
        'calidad_cms_ventanas': _calidad(rows, 'cms_ventanas'),
        'tiempos_fallidos': pd.DataFrame(fallidas),
    }
    for name, table in tables.items():
        if not len(table.columns):
            table = tables[name] = pd.DataFrame(columns=['sin_observaciones'])
        table.to_csv(tables_dir / f'{name}.csv', index=False)
        (tables_dir / f'{name}.md').write_text(markdown_table(table) + '\n', encoding='utf-8')

    plt.rcParams.update({'font.size': 9, 'axes.spines.top': False, 'axes.spines.right': False})
    captions = []

    def save(fig, name, caption):
        fig.tight_layout()
        for extension in ('png', 'svg', 'pdf'):
            fig.savefig(figures_dir / f'{name}.{extension}', dpi=180, bbox_inches='tight')
        plt.close(fig)
        captions.append((name, caption))

    parametros = evidence.get('parametros', {})
    for columna, desviacion, nombre, etiqueta in (
            ('construccion_ms_media', 'construccion_ms_desv', 'tiempos_construccion', 'Construcción (ms)'),
            ('operacion_us_media', 'operacion_us_desv', 'tiempos_operacion', 'Tiempo por operación (µs)')):
        if tabla.empty:
            break
        fig, axes = plt.subplots(1, 3, figsize=(13, 4))
        for ax, (titulo, casos) in zip(axes, GRUPOS.items()):
            for caso in casos:
                grupo = tabla[(tabla['caso'] == caso) & tabla[columna].notna()]
                if not grupo.empty:
                    ax.errorbar(grupo['n'], grupo[columna], yerr=grupo[desviacion].fillna(0), marker='o',
                                markersize=3, capsize=2, label=caso)
            ax.set(xscale='log', yscale='log', xlabel='n (carga real de la estructura)', ylabel=etiqueta, title=titulo)
            ax.grid(alpha=.25, which='both')
            if ax.has_data():
                ax.legend(fontsize=7)
        repeticiones = (f'{parametros.get("repeticiones_construccion")} construcciones por punto'
                        if columna.startswith('construccion') else
                        f'{parametros.get("repeticiones_operacion")} repeticiones de un lote fijo de consultas por punto')
        save(fig, nombre, f'{etiqueta} frente a n en escala log-log; {repeticiones}; barras = desviación estándar. '
             'La pendiente de cada recta es el exponente observado; tiempos_pendientes.csv la contrasta con la '
             'complejidad esperada (pendiente ≈ 1 para O(n) y O(n log n); ≈ 0 para O(1) y O(log n)).')

    bloom, cms = tables['calidad_bloom'], tables['calidad_cms']
    if 'fp_observada' in bloom.columns or 'mae' in cms.columns:
        fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
        if 'fp_observada' in bloom.columns:
            axes[0].plot(bloom['n'], bloom['fp_observada'] * 100, 'o-', label='Observada (100.000 ausentes)')
            axes[0].plot(bloom['n'], bloom['fp_teorica'] * 100, 's--', label='Teórica (1 − e^(−kn/m))^k')
            axes[0].axhline(bloom['fp_objetivo'].iloc[0] * 100, linestyle=':', color='#b34835', label='Objetivo')
            axes[0].set(xscale='log', xlabel='Claves únicas insertadas', ylabel='Falsos positivos (%)',
                        title='Bloom Filter')
            axes[0].legend(fontsize=7)
        if 'mae' in cms.columns:
            axes[1].plot(cms['total_actualizaciones'], cms['mae'], 'o-', label='Error absoluto medio')
            axes[1].plot(cms['total_actualizaciones'], cms['error_maximo'], 's-', label='Error máximo')
            axes[1].plot(cms['total_actualizaciones'], cms['cota_error'], ':', label='Cota ε·N (prob. 1 − δ)')
            axes[1].set(xscale='log', yscale='symlog', xlabel='Actualizaciones N', ylabel='Sobreestimación (conteos)',
                        title=f'Count-Min Sketch ({int(cms["ancho"].iloc[0])} × {int(cms["profundidad"].iloc[0])})')
            axes[1].legend(fontsize=7)
        for ax in axes:
            ax.grid(alpha=.25, which='both')
        save(fig, 'calidad_probabilisticas',
             'Izquierda: tasa de falsos positivos de Bloom con 100.000 claves ausentes, frente a la teórica y al '
             'objetivo configurado. Derecha: error de CMS sobre todas las claves de pago reales; nunca subestima, y '
             'la cota ε·N con ε = e/ancho se cumple con probabilidad 1 − δ, δ = e^(−profundidad).')

    notas = ['# Campaña de tiempos por estructura y escala',
             f'Fecha UTC: {evidence["fecha_utc"]}. Semilla: {parametros.get("semilla")}. '
             f'Construcciones por caso: {parametros.get("repeticiones_construccion")}; repeticiones del lote de '
             f'operaciones: {parametros.get("repeticiones_operacion")}.',
             f'Plataforma: {parametros.get("plataforma")}.',
             'Cada caso corre en un proceso nuevo con su entrada ya cargada; solo se cronometra la estructura. '
             'n es la carga real de cada estructura (eventos, órdenes, productos, claves, vectores o conjuntos), '
             'no el número de eventos del archivo. La construcción se repite pocas veces porque en 1M y 10M es la '
             'operación cara; la operación típica se repite sobre un lote fijo y se reporta por operación.',
             '## Exponentes observados en log-log', markdown_table(tables['tiempos_pendientes'].round(3)),
             'Una pendiente cercana a 1 corresponde a crecimiento lineal (O(n) y, en la práctica, O(n log n)); '
             'cercana a 0, a costo constante o logarítmico. R² bajo indica ruido o pocas escalas.',
             '## Probabilísticas frente a exactas (tiempo)', markdown_table(tables['probabilisticas_vs_exactas'].round(4)),
             '## Calidad de Bloom', markdown_table(tables['calidad_bloom'].round(5)),
             '## Error de Count-Min Sketch', markdown_table(tables['calidad_cms'].round(4)),
             '## Error de CMS por ventanas (al final del flujo)', markdown_table(tables['calidad_cms_ventanas'].round(4)),
             '## Tiempos por caso y escala', markdown_table(tabla.round(4)) if not tabla.empty else 'Sin mediciones.']
    if fallidas:
        notas.extend(['## Mediciones fallidas', markdown_table(tables['tiempos_fallidos'])])
    notas.append('## Figuras')
    for name, caption in captions:
        notas.extend([f'### {name}', f'![{name}](figuras/{name}.png)', caption])
    (output / 'resumen_tiempos.md').write_text('\n\n'.join(notas) + '\n', encoding='utf-8')
    return tables
