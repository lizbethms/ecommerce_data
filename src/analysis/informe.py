"""Tablas y figuras derivadas únicamente de evidencia persistida."""
from pathlib import Path
import math
import os
import tempfile

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'ecommerce-demo-matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd


def markdown_table(frame):
    if frame.empty:
        return '_Sin observaciones para esta tabla._'
    def cell(value):
        if pd.api.types.is_scalar(value) and pd.isna(value):
            return '—'
        return str(value).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join([
        '| ' + ' | '.join(map(str, frame.columns)) + ' |',
        '| ' + ' | '.join('---' for _ in frame.columns) + ' |',
        *['| ' + ' | '.join(cell(v) for v in row) + ' |'
          for row in frame.itertuples(index=False, name=None)],
    ])


def export_report(evidence, output, memory_evidence=None):
    output = Path(output)
    tables_dir, figures_dir = output / 'tablas', output / 'figuras'
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    g = evidence['grafo']
    panel = evidence['servicio']['panel']
    ingesta = panel['ingesta']
    alertas = panel['alertas']
    fraude = evidence['estadisticas']['fraude']
    nodes = pd.DataFrame(g['nodos'])
    measurements = pd.DataFrame(evidence['mediciones'])
    summary = measurements.groupby(['familia', 'algoritmo'], as_index=False).agg(
        media_ms=('latencia_ms', 'mean'), desviacion_ms=('latencia_ms', 'std'),
        mediana_ms=('latencia_ms', 'median'), p95_ms=('latencia_ms', lambda s: s.quantile(.95)),
        observaciones=('latencia_ms', 'size'), consultas_distintas=('consulta', 'nunique'),
        recall_empates=('recall_empates', 'mean'))
    coverage = pd.DataFrame([
        dict(requisito='Prioridades', evidencia='prioridades.csv; control.consultas',
             conclusion='Alerta → express → estándar → programada en el escenario controlado'),
        dict(requisito='Filtrado probabilístico', evidencia='bloom.csv; cms.csv; control.bloom_calidad',
             conclusion='Pertenencia e intensidad se verifican con registros exactos'),
        dict(requisito='Similitud vectorial y de conjuntos', evidencia='similitud_resumen.csv; vecinos*.csv',
             conclusion='Referencias exhaustivas sobre el índice completo; calidad con empates'),
        dict(requisito='Grafo', evidencia='grafo_resumen.csv; nodos.csv; aristas.csv; comunidades.csv',
             conclusion='Grafo inducido por compras aceptadas; Label Propagation pendiente'),
        dict(requisito='Servicio al usuario', evidencia='busqueda.csv; complementarios.csv; recomendaciones.csv',
             conclusion='Búsqueda, similitud y co-compra alimentan respuestas de la API'),
    ])
    tables = {
        'cobertura': coverage,
        'fuente': pd.DataFrame([dict(eventos_archivo=evidence['fuente']['filas'],
                                    **evidence['fuente']['estados'],
                                    vectores=evidence['estadisticas']['recomendacion']['vectores'],
                                    conjuntos=evidence['estadisticas']['recomendacion']['conjuntos_minhash'])]),
        'composicion': pd.DataFrame([
            dict(origen=origin, eventos=count, proporcion=count / evidence['fuente']['filas'])
            for origin, count in evidence['fuente']['origenes'].items()]),
        'tipos_evento': pd.DataFrame([
            dict(tipo=kind, eventos=count) for kind, count in evidence['fuente']['tipos'].items()]),
        'tipos_aceptados': pd.DataFrame([
            dict(tipo=kind, eventos=count) for kind, count in panel['actividad']['por_tipo'].items()]),
        'origenes_aceptados': pd.DataFrame([
            dict(origen=origin, eventos=count) for origin, count in panel['actividad']['por_origen'].items()]),
        'fraude_resumen': pd.DataFrame([dict(alertas=alertas['total'], alertas_bloqueadas=alertas['bloqueos'],
                                         alertas_en_revision=alertas['total'] - alertas['bloqueos'],
                                         pagos_permitidos=fraude['decisiones']['permitir'],
                                         pagos_para_revision=fraude['decisiones']['revisar'],
                                         pagos_bloqueados=fraude['decisiones']['bloquear'])]),
        'ventas_resumen': pd.DataFrame([panel['ventas']]),
        'cola_resumen': pd.DataFrame([{key: value for key, value in panel['cola_ordenes'].items()
                                      if key not in ('siguientes', 'encoladas')}]),
        'prioridades': pd.DataFrame(evidence['control']['atendidos']),
        'bloom': pd.DataFrame(evidence['control']['bloom']),
        'bloom_calidad': pd.DataFrame([evidence['control']['bloom_calidad']]),
        'cms': pd.DataFrame(evidence['control']['cms']),
        'pagos_historico': pd.DataFrame(evidence['pagos_historico']),
        'similitud_mediciones': measurements,
        'similitud_resumen': summary,
        'vecinos': pd.DataFrame(evidence['vecinos']),
        'vecinos_conjuntos': pd.DataFrame(evidence['vecinos_conjuntos']),
        'grafo_resumen': pd.DataFrame([g['resumen']]),
        'evolucion_grafo': pd.DataFrame(evidence['evolucion_grafo']),
        'nodos': nodes,
        'aristas': pd.DataFrame(g['aristas'], columns=['producto_a', 'producto_b', 'ordenes_compartidas']),
        'comunidades': pd.DataFrame(g['comunidades'], columns=['comunidad', 'productos']),
        'busqueda': pd.DataFrame(evidence['servicio']['busqueda']['resultados']),
        'rango_precios': pd.DataFrame(evidence['servicio']['rango']['resultados']),
        'complementarios': pd.DataFrame(evidence['servicio']['complementarios']),
        'recomendaciones': pd.DataFrame(evidence['servicio']['recomendaciones']['resultados']),
        'consultas': pd.DataFrame([
            {key: value for key, value in r.items() if key not in ('respuesta', 'cuerpo')}
            for r in evidence['consultas']]),
    }
    # Columnas explícitas conservan CSV legibles también cuando no hubo resultados.
    for name, table in tables.items():
        if not len(table.columns):
            table = tables[name] = pd.DataFrame(columns=['sin_observaciones'])
        table.to_csv(tables_dir / f'{name}.csv', index=False)
        (tables_dir / f'{name}.md').write_text(markdown_table(table) + '\n', encoding='utf-8')

    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    captions = []

    def save(fig, name, caption):
        fig.tight_layout()
        for extension in ('png', 'svg', 'pdf'):
            fig.savefig(figures_dir / f'{name}.{extension}', dpi=180, bbox_inches='tight')
        plt.close(fig)
        captions.append((name, caption.strip()))

    fig, ax = plt.subplots(figsize=(9, 3.4))
    priorities = tables['prioridades']
    labels = {'alerta': 'Alerta por pago fallido', 'express': 'Entrega exprés',
              'standard': 'Entrega estándar', 'scheduled': 'Entrega programada'}
    classes = [row['delivery_type'] if row['tipo'] == 'orden' else 'alerta'
               for _, row in priorities.iterrows()]
    positions = list(range(1, len(priorities) + 1))
    y = list(range(len(priorities), 0, -1))
    ax.scatter(positions, y, s=520, c=['#b34835' if c == 'alerta' else '#267c9c' for c in classes], zorder=3)
    for x, yy in zip(positions, y):
        ax.text(x, yy, str(x), ha='center', va='center', color='white', weight='bold', zorder=4)
    ax.set(yticks=y, yticklabels=[labels[c] for c in classes], xticks=positions,
           xlabel='Turno de atención (1 = primero)', xlim=(.5, len(positions) + .5),
           ylim=(.5, len(positions) + .5), title=f'Secuencia de atención: {len(priorities)} elementos, uno por categoría')
    ax.grid(axis='x', alpha=.25)
    save(fig, '01_prioridades',
         'Escenario controlado y aislado: hay una alerta y una orden de cada modalidad; los números indican turno, no cantidad. '
         'La alerta por pago fallido se atiende primero. Exprés vence 4 h después de llegar; estándar, 48 h después; '
         'programada, en la fecha pactada. Entre órdenes se atiende el plazo más próximo; consultar llegadas y plazos en prioridades.csv.')

    fig, ax = plt.subplots(figsize=(7, 3.5))
    cms = tables['cms']
    ax.plot(cms['intento'], cms['estimado_cms'], 'o-', label='CMS por ventanas')
    ax.plot(cms['intento'], cms['exacto'], 'x--', label='Conteo exacto')
    threshold = evidence['metadata']['configuracion']['umbral_intentos']
    ax.axhline(threshold, linestyle=':', color='#b34835', label=f'Umbral de bloqueo: {threshold}')
    ax.set(xticks=cms['intento'], xlabel='Número de intento del mismo usuario',
           ylabel='Intentos acumulados en la ventana', title='Conteo de seis pagos en una ventana de 10 minutos')
    for _, row in cms.iterrows():
        ax.annotate(str(row['exacto']), (row['intento'], row['exacto']), xytext=(0, 8),
                    textcoords='offset points', ha='center', fontsize=8)
    ax.legend()
    blocked = cms.loc[cms['decision'] == 'bloquear', 'intento'].tolist()
    save(fig, '02_cms', f'Cada punto representa un pago sintético del mismo usuario dentro de 600 s. '
         f'CMS es una estimación; el conteo exacto confirma el umbral de {threshold}. '
         f'En este escenario se bloquean los intentos {", ".join(map(str, blocked)) or "ninguno"}. '
         'No se prueban los bordes de la ventana ni la ausencia de colisiones en otros datos.')

    for family, name in [('vectorial', '03_similitud_vectorial'), ('conjuntos', '04_similitud_conjuntos')]:
        selected = summary[summary['familia'] == family]
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        if selected.empty:
            for ax in axes:
                ax.text(.5, .5, 'Sin consultas elegibles', ha='center', transform=ax.transAxes)
        else:
            latency_bars = axes[0].bar(selected['algoritmo'], selected['media_ms'], color='#267c9c')
            axes[0].set(ylabel='Latencia media de consulta pura (ms)')
            axes[0].bar_label(latency_bars, fmt='%.3f', padding=3, fontsize=8)
            recall_bars = axes[1].bar(selected['algoritmo'], selected['recall_empates'] * 100, color='#4b9676')
            axes[1].bar_label(recall_bars, fmt='%.0f%%', padding=3, fontsize=8)
            axes[1].set(ylabel=f'Vecinos correctos, recall@{evidence["metadata"]["k"]} (%)', ylim=(0, 112))
            axes[0].set_ylim(0, selected['media_ms'].max() * 1.18)
            for ax in axes:
                ax.tick_params(axis='x', labelrotation=20)
        method_note = ('Fuerza bruta compara todos los vectores; KD-Tree busca vecinos exactos; HNSW aproxima la búsqueda.'
                       if family == 'vectorial' else
                       'Jaccard exhaustivo compara todos los conjuntos de usuarios; MinHash/LSH aproxima los candidatos.')
        save(fig, name, f'{method_note} Izquierda: media de {int(selected["observaciones"].iloc[0]) if not selected.empty else 0} '
             f'consultas por método sobre índices fijos, en milisegundos (menos es mejor). Derecha: porcentaje de los '
             f'{evidence["metadata"]["k"]} vecinos esperados encontrados, aceptando empates (más es mejor). '
             'El producto consultado se excluye. La dispersión y las consultas distintas figuran en similitud_resumen.csv. '
             + ('Para conjuntos, un Jaccard máximo de cero puede inflar la calidad aparente; ver referencia_positiva.'
                if family == 'conjuntos' else ''))

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.5))
    evolution = tables['evolucion_grafo']
    axes[0].plot(evolution['eventos_leidos'], evolution['V'], 'o-', label='Productos (V)')
    axes[0].plot(evolution['eventos_leidos'], evolution['E'], 's-', label='Pares distintos (E)')
    axes[0].set(xlabel='Filas leídas del archivo', ylabel='Cantidad', title='Productos y pares de co-compra')
    axes[0].legend()
    axes[1].plot(evolution['eventos_leidos'], evolution['peso_total'], 'o-', color='#4b9676')
    axes[1].set(xlabel='Filas leídas del archivo', ylabel='Suma de órdenes compartidas', title='Peso total de los pares')
    last = evolution.iloc[-1]
    for ax, columns in [(axes[0], [('V', 'V'), ('E', 'E')]), (axes[1], [('peso_total', 'Peso')])]:
        for column, label in columns:
            ax.annotate(f'{label}={int(last[column])}', (last['eventos_leidos'], last[column]),
                        xytext=(-8, 8 if label != 'V' else -15), textcoords='offset points', ha='right', fontsize=8)
        ax.grid(alpha=.2)
    save(fig, '05_evolucion_grafo',
         f'Una sola reproducción de {int(last["eventos_leidos"]):,} filas, con {int(last["eventos_aceptados"]):,} '
         f'eventos aceptados. V={int(last["V"])} productos comprados; E={int(last["E"])} pares distintos; '
         f'peso total={int(last["peso_total"])} órdenes compartidas sumadas sobre los pares. '
         'Los puntos son acumulativos; más peso no implica necesariamente más pares.')

    fig, ax = plt.subplots(figsize=(8, 3.5))
    communities = tables['comunidades'].sort_values('productos', ascending=False).head(20)
    if not communities.empty:
        bars = ax.bar(communities['comunidad'].astype(str), communities['productos'], color='#267c9c')
        ax.bar_label(bars, padding=2, fontsize=8)
        ax.set_ylim(0, communities['productos'].max() * 1.14)
    else:
        ax.text(.5, .5, 'No hay productos con co-compra', ha='center', transform=ax.transAxes)
    ax.set(xlabel='Identificador de comunidad', ylabel='Productos por comunidad',
           title=f'Comunidades de mayor tamaño ({len(communities)} de {g["resumen"]["comunidades"]})')
    ax.tick_params(axis='x', labelrotation=45)
    save(fig, '06_comunidades',
         f'Louvain agrupa productos conectados por compras conjuntas. Se muestran {len(communities)} de '
         f'{g["resumen"]["comunidades"]} comunidades, formadas sobre {g["resumen"]["V_analisis"]} productos; '
         f'los {g["resumen"]["aislados"]} productos sin pares quedan fuera. '
         f'Modularidad={g["resumen"]["modularidad"]:.4f}; una sola partición, sin estudio de estabilidad.')

    fig, ax = plt.subplots(figsize=(10, 4.8))
    ranked = nodes.dropna(subset=['pagerank']).copy() if not nodes.empty else nodes
    if not ranked.empty:
        ranked['puesto_pagerank'] = ranked['pagerank'].rank(method='min', ascending=False)
        ranked['puesto_grado'] = ranked['grado_ponderado'].rank(method='min', ascending=False)
        top = ranked.sort_values(['puesto_pagerank', 'product_id']).head(10)
        pos = list(range(len(top)))
        for yy, (_, row) in zip(pos, top.iterrows()):
            ax.plot([row['puesto_pagerank'], row['puesto_grado']], [yy - .12, yy + .12],
                    color='#bdcbd1', zorder=1)
        ax.scatter(top['puesto_pagerank'], [yy - .12 for yy in pos], color='#267c9c',
                   label='PageRank', zorder=3)
        ax.scatter(top['puesto_grado'], [yy + .12 for yy in pos], color='#b34835',
                   marker='s', label='Grado ponderado', zorder=3)
        ax.set_yticks(pos, top['product_id'].astype(str))
        ax.invert_yaxis()
        ax.legend()
    ax.set(xlabel='Posición en el ranking (menor = mejor)', ylabel='Producto',
           title=f'Los {min(10, len(ranked))} primeros por PageRank frente al grado ponderado')
    ax.grid(axis='x', alpha=.2)
    save(fig, '07_influencia',
         f'Se eligen los {min(10, len(ranked))} productos mejor ubicados por PageRank entre '
         f'{len(ranked)} productos con co-compra. Cada par de puntos muestra su posición según PageRank y según '
         'el grado ponderado (suma de órdenes compartidas con sus vecinos). Estar más a la izquierda significa mejor posición.')

    # Vista parcial determinista; nunca se usa para calcular las métricas globales.
    fig, ax = plt.subplots(figsize=(9, 8))
    selected = (nodes.dropna(subset=['pagerank']).sort_values(
        ['pagerank', 'product_id'], ascending=[False, True]).head(30) if not nodes.empty else nodes)
    ids = selected['product_id'].tolist() if not selected.empty else []
    positions = {p: (math.cos(2 * math.pi * i / len(ids)), math.sin(2 * math.pi * i / len(ids)))
                 for i, p in enumerate(ids)}
    visible = 0
    for edge in g['aristas']:
        u, v, weight = edge['producto_a'], edge['producto_b'], edge['ordenes_compartidas']
        if u in positions and v in positions:
            visible += 1
            ax.plot([positions[u][0], positions[v][0]], [positions[u][1], positions[v][1]],
                    color='#b7c4cb', alpha=.6, linewidth=min(4, .5 + math.log1p(weight)), zorder=1)
    for row in selected.to_dict('records'):
        p = row['product_id']
        x, y = positions[p]
        ax.scatter(x, y, s=120 + 900 * row['pagerank'] / selected['pagerank'].max(),
                   color=plt.get_cmap('tab20')(int(row['comunidad']) % 20), zorder=2)
        alignment = 'left' if x > .2 else 'right' if x < -.2 else 'center'
        ax.text(x * 1.08, y * 1.08, p, ha=alignment, va='center', fontsize=8)
    ax.set_title(f'Vista parcial: {len(ids)}/{g["resumen"]["V_analisis"]} productos con co-compra; {visible} aristas visibles')
    ax.set_aspect('equal')
    ax.set_xlim(-1.4, 1.4)
    ax.set_ylim(-1.3, 1.3)
    ax.axis('off')
    save(fig, '08_subgrafo',
         f'Vista parcial de {len(ids)} de {g["resumen"]["V_analisis"]} productos con co-compra y '
         f'{visible} de {g["resumen"]["E"]} pares. Cada círculo es un producto; su tamaño relativo indica PageRank. '
         'Una línea une productos comprados en la misma orden; su grosor aumenta con el número de órdenes '
         'compartidas. El color indica comunidad (20 colores que pueden repetirse). La posición circular es '
         'ilustrativa; las métricas se calculan sobre el grafo completo.')

    notes = [
        '# Evidencia de la demo técnica',
        f'Corrida UTC: {evidence["metadata"]["fecha_utc"]}. Semilla: {evidence["metadata"]["semilla"]}.',
        f'Fuente: `{evidence["metadata"]["datos"]}`. Informe de una reproducción aislada y finalizada; '
        'el dashboard consulta otra API en memoria y solo coincide tras enviarle el mismo archivo completo, '
        'con la misma configuración y sin tráfico adicional.',
        '## Cobertura', markdown_table(coverage),
        '## Población observada', markdown_table(tables['fuente']),
        markdown_table(tables['composicion']),
        'Los conteos de composición y tipos del archivo incluyen duplicados; el dashboard muestra solo eventos '
        'aceptados. La muestra preparada incorpora escenarios sintéticos; '
        'sus proporciones no representan necesariamente el histórico completo.',
        '### Eventos aceptados por tipo', markdown_table(tables['tipos_aceptados']),
        '### Eventos aceptados por origen', markdown_table(tables['origenes_aceptados']),
        '## Resumen del monitor al finalizar la reproducción',
        'Las alertas son órdenes señaladas, no fraudes confirmados. Una alerta puede reunir varios intentos '
        'de pago y escalar de revisión a bloqueo; por ello las decisiones por intento no suman el número de alertas.',
        markdown_table(tables['fraude_resumen']),
        '### Ventas', markdown_table(tables['ventas_resumen']),
        '### Cola de órdenes', markdown_table(tables['cola_resumen']),
        'La prueba de idempotencia posterior al snapshot añade un duplicado a las estadísticas finales de '
        '`evidencia.json`; la tabla de población y esta sección reflejan el estado anterior a esa prueba.',
        markdown_table(tables['grafo_resumen'][['V_total', 'V_analisis', 'E', 'aislados', 'comunidades', 'modularidad']]),
        '## Similitud', markdown_table(summary.round(5)),
        'La desviación resume consultas y repeticiones en índices fijos; no representa construcciones independientes. '
        'Con una observación la desviación no es estimable. El tiempo HTTP incluye transporte ASGI, enriquecimiento y referencias '
        'del endpoint; se conserva aparte de la consulta pura.',
        '## Figuras y pies reutilizables',
    ]
    for name, caption in captions:
        notes.extend([f'### {name}', f'![{name}](figuras/{name}.png)', caption])
    if memory_evidence is not None:
        from src.analysis.informe_memoria import memory_section
        notes.append(memory_section(memory_evidence, output))
    notes.extend([
        '## Alcance y pendientes',
        'Esta corrida es una demo funcional y un piloto, no sustituye la campaña de 100 repeticiones independientes, '
        'las cinco escalas ni la evaluación completa de memoria por estructura. No se han medido aquí tiempos de construcción aislados. '
        'PageRank y Louvain se cronometran una vez sobre la misma instantánea completa sin aislados; '
        'no se estima dispersión con n=1. Label Propagation y estabilidad de comunidades siguen pendientes.',
        'El tamaño principal de integración se expresa en eventos. V y E son resultados de las compras aceptadas; '
        'no se fuerza un catálogo sintético para igualar el número de eventos. La suficiencia de esta interpretación '
        'para las escalas obligatorias del curso sigue sujeta a confirmación docente.',
        'El CMS del escenario controlado evita los bordes de ventana. Las diferencias temporales del histórico '
        'no deben atribuirse automáticamente a colisiones. La FPR del escenario aislado no caracteriza el tráfico completo.',
        'La API admite compras bloqueadas en sus otros servicios y retiene la orden al atenderla. El grafo actual registra '
        'compras aceptadas por ingesta, no exclusivamente despachos autorizados. Las devoluciones no deshacen sus aristas.',
        'El transporte del notebook es HTTP ASGI en proceso. La FIFO de ingesta no forma parte de esta ruta; '
        'no se atribuye esta evidencia a un recorrido integrado de diez etapas.',
    ])
    (output / 'resumen.md').write_text('\n\n'.join(notes) + '\n', encoding='utf-8')
    (figures_dir / 'pies.md').write_text('\n\n'.join(f'**{name}.** {caption}' for name, caption in captions) + '\n', encoding='utf-8')
    return tables
