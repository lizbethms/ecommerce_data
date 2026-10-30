"""Consultas HTTP aisladas y referencias completas; no constituye un benchmark de escala."""
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
from itertools import combinations, islice
from functools import partial
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import time

from fastapi.testclient import TestClient

from API_SERVICIOS.config import Config
from API_SERVICIOS.main import create_app
from src.data.parquet_io import iter_events
from src.data.prepare import digest_file
from src.structures.graph import WeightedGraph, louvain, modularity, pagerank
from src.structures.kd_tree import squared_distance
from src.structures.minhash_lsh import jaccard


def recall_with_ties(scores, returned, k, higher=False):
    """Acepta empates en el límite, exigiendo también los vecinos estrictamente mejores."""
    count = min(k, len(scores))
    if not count:
        return None
    boundary = sorted(scores.values(), reverse=higher)[count - 1]
    tied = {p for p, s in scores.items() if math.isclose(s, boundary, abs_tol=1e-12, rel_tol=1e-9)}
    better = {p for p, s in scores.items() if p not in tied and (s > boundary if higher else s < boundary)}
    found = set(returned[:count])
    return (len(found & better) + min(len(found & tied), count - len(better))) / count


def record_request(client, records, method, route, **kwargs):
    """Ejecuta una consulta y conserva su respuesta y latencia en la corrida."""
    start = time.perf_counter_ns()
    response = client.request(method, route, **kwargs)
    elapsed = (time.perf_counter_ns() - start) / 1e6
    response.raise_for_status()
    result = response.json()
    records.append(dict(metodo=method, ruta=route, parametros=kwargs.get('params', {}),
                        cuerpo=kwargs.get('json'), estado_http=response.status_code,
                        latencia_http_ms=elapsed, respuesta=result))
    return result


def controlled_scenes():
    """Escenarios sintéticos separados del histórico: prioridad y verificación de fraude."""
    records = []
    app = create_app(Config(dir_datos=None, precargar=False))
    with TestClient(app) as client:
        q = partial(record_request, client, records)

        def event(eid, kind, date, **extra):
            return dict(event_id=eid, event_type=kind, event_time=date,
                        user_id='demo:comprador', user_session='demo:sesion', product_id='demo:A',
                        category_id='demo:categoria', category_code='electronics.audio', brand='demo',
                        price='50.00', event_origin='synthetic', **extra)

        events = [
            event('demo:std', 'purchase', '2019-10-01T08:00:00Z', order_id='demo:estandar',
                  quantity=1, delivery_type='standard'),
            event('demo:exp', 'purchase', '2019-10-01T08:01:00Z', order_id='demo:express',
                  quantity=1, delivery_type='express'),
            event('demo:prog', 'purchase', '2019-10-01T08:02:00Z', order_id='demo:programada',
                  quantity=1, delivery_type='scheduled', scheduled_at='2019-10-04T08:00:00Z'),
            event('demo:fallido', 'payment_attempt', '2019-10-01T08:03:00Z', order_id='demo:alerta',
                  payment_attempt_id='demo:intento', payment_method_id='demo:medio',
                  device_id='demo:dispositivo', payment_status='failed'),
        ]
        received = q('POST', '/eventos/lote', json=list(reversed(events)))
        if received['resumen'] != {'aceptado': 4}:
            raise AssertionError(received)
        queue = q('GET', '/ordenes/cola')['siguientes']
        served = q('POST', '/ordenes/atender', params={'n': 4})['atendidos']
        expected = ['demo:alerta', 'demo:express', 'demo:estandar', 'demo:programada']
        if [x['order_id'] for x in served] != expected:
            raise AssertionError('La atención no coincide con la prioridad esperada')

        q('POST', '/fraude/senalados', params={'tipo': 'account', 'valor': 'demo:senalado'})
        bloom_cases = []
        for user in ('demo:senalado', 'demo:limpio'):
            result = q('POST', '/fraude/verificar', json={'user_id': user})
            key = f'account:{user}'
            f = app.state.sistema.fraude
            bloom_cases.append(dict(cuenta=user, bloom_positivo=key in f.bloom,
                                    exacto_positivo=key in f.senalados, decision=result['decision']))
        # Búsqueda determinista de FP en ausentes, sin fabricar una colisión ni exigir que ocurra.
        f = app.state.sistema.fraude
        fp_count = sum(f'account:demo:ausente:{i}' in f.bloom for i in range(10000))
        false_negatives = sum(key not in f.bloom for key in f.senalados.keys())
        intensity = []
        for i in range(6):
            payment = event(f'demo:cms:{i}', 'payment_attempt', f'2019-10-01T08:04:{i:02d}Z',
                            order_id='demo:intensidad', payment_attempt_id=f'demo:pa:{i}',
                            payment_status='succeeded', device_id='demo:cms:device',
                            payment_method_id='demo:cms:method')
            payment['user_id'] = 'demo:cms:user'
            result = q('POST', '/eventos', json=payment)
            if result['estado'] != 'aceptado':
                raise AssertionError(result)
            fraud = result['resultados']['fraude']
            values = fraud['intensidad']['account:demo:cms:user']
            intensity.append(dict(intento=i + 1, **values, decision=fraud['decision']))
        return dict(origen='sintético controlado; excluido del grafo del histórico', eventos=events,
                    cola=queue, atendidos=served, bloom=bloom_cases, cms=intensity,
                    bloom_calidad=dict(ausentes=10000, falsos_positivos=fp_count,
                                       fpr=fp_count / 10000, falsos_negativos=false_negatives),
                    consultas=records)


def similarity_measurements(service, seed, k, queries, repetitions):
    """Consulta pura; referencias y calidad se calculan fuera del intervalo medido."""
    rng = random.Random(seed)
    ids = sorted(service.vectores)
    selected = rng.sample(ids, min(queries, len(ids)))
    rows, neighbors = [], []
    for pid in selected:
        vector = service.vectores[pid]
        def brute():
            return sorted(((p, math.sqrt(squared_distance(vector, v)))
                           for p, v in service.vectores.items() if p != pid),
                          key=lambda item: (item[1], item[0]))[:k]
        methods = {'fuerza_bruta': brute,
                   'kd_tree': lambda: service.kd.knn(vector, k, exclude=pid),
                   'hnsw': lambda: service.hnsw.search(vector, k, exclude=pid)}
        scores = {p: math.sqrt(squared_distance(vector, v))
                  for p, v in service.vectores.items() if p != pid}
        reference = brute()
        for method in methods.values():
            method()  # calentamiento de consulta, fuera de las mediciones
        for repetition in range(repetitions):
            order = list(methods)
            rng.shuffle(order)
            for name in order:
                start = time.perf_counter_ns()
                result = methods[name]()
                elapsed = (time.perf_counter_ns() - start) / 1e6
                recall = recall_with_ties(scores, [p for p, _ in result], k)
                if name == 'kd_tree' and recall != (1.0 if scores else None):
                    raise AssertionError('KD-Tree no coincide con fuerza bruta, considerando empates')
                strict = (len({p for p, _ in reference} & {p for p, _ in result}) / len(reference)
                          if reference else None)
                rows.append(dict(familia='vectorial', consulta=pid, algoritmo=name,
                                 repeticion=repetition, latencia_ms=elapsed, k=k,
                                 candidatos_indice=len(ids), recall_empates=recall, recall_ids=strict))
                if repetition == 0:
                    neighbors.extend(dict(consulta=pid, algoritmo=name, posicion=i + 1,
                                          product_id=p, distancia=d) for i, (p, d) in enumerate(result))

    sets = service.usuarios_por_producto
    selected_sets = rng.sample(sorted(sets), min(queries, len(sets)))
    set_rows = []
    for pid in selected_sets:
        scores = {p: jaccard(sets[pid], users) for p, users in sets.items() if p != pid}
        methods = {
            'jaccard_exhaustivo': lambda: sorted(
                ((p, jaccard(sets[pid], users)) for p, users in sets.items() if p != pid),
                key=lambda item: (-item[1], item[0]))[:k],
            'minhash_lsh': lambda: service.lsh.query(pid, k),
        }
        for method in methods.values():
            method()
        for repetition in range(repetitions):
            order = list(methods)
            rng.shuffle(order)
            for name in order:
                start = time.perf_counter_ns()
                result = methods[name]()
                elapsed = (time.perf_counter_ns() - start) / 1e6
                rows.append(dict(familia='conjuntos', consulta=pid, algoritmo=name,
                                 repeticion=repetition, latencia_ms=elapsed, k=k,
                                 candidatos_indice=len(sets),
                                 referencia_positiva=any(s > 0 for s in scores.values()),
                                 recall_empates=recall_with_ties(scores, [p for p, _ in result], k, True),
                                 recall_ids=None))
                if repetition == 0:
                    set_rows.extend(dict(consulta=pid, algoritmo=name, posicion=i + 1, product_id=p,
                                         jaccard_mostrado=s, jaccard_exacto=scores[p])
                                    for i, (p, s) in enumerate(result))
    return rows, neighbors, set_rows


def graph_snapshot(system, expected_orders):
    graph = system.cocompra.grafo
    actual = {tuple(sorted((u, v))): w for u, v, w in graph.edges()}
    expected = Counter(pair for products in expected_orders.values()
                       for pair in combinations(sorted(products), 2))
    if actual != dict(expected):
        raise AssertionError('El grafo no coincide con los pares por órdenes aceptadas')
    # Replica explícitamente la población analizada por ServicioCoCompra._analisis().
    analyzed = WeightedGraph()
    # Conservar también el orden de inserción: con la misma semilla influye en Louvain.
    for u, v, w in graph.edges():
        analyzed.add_edge(u, v, w)
    start = time.perf_counter_ns()
    ranks = pagerank(analyzed)
    pr_ms = (time.perf_counter_ns() - start) / 1e6
    start = time.perf_counter_ns()
    partition = louvain(analyzed, seed=system.config.semilla)
    louvain_ms = (time.perf_counter_ns() - start) / 1e6
    api_ranks, api_partition, _ = system.cocompra._analisis()
    if partition != api_partition or ranks != api_ranks:
        raise AssertionError('La instantánea exportada no coincide con el análisis del servicio')
    counts = Counter(partition.values())
    nodes = [dict(product_id=p, nombre=system.catalogo.registro(p)['nombre'],
                  vecinos=len(graph.neighbors(p)), grado_ponderado=graph.degree(p),
                  comunidad=partition.get(p), pagerank=ranks.get(p), analizado=p in partition)
             for p in sorted(graph.nodes())]
    edges = [dict(producto_a=u, producto_b=v, ordenes_compartidas=w)
             for (u, v), w in sorted(actual.items())]
    canonical = json.dumps(dict(nodos=sorted(graph.nodes()), aristas=edges), sort_keys=True)
    summary = dict(V_total=len(nodes), V_analisis=len(partition), E=len(edges),
                   aislados=len(nodes) - len(partition), peso_total=graph.total_weight(),
                   grado_medio=2 * len(edges) / len(nodes) if nodes else 0,
                   componentes=len(graph.connected_components()),
                   comunidades=len(counts), modularidad=modularity(analyzed, partition),
                   pagerank_ms=pr_ms, louvain_ms=louvain_ms, repeticiones=1,
                   sha256=hashlib.sha256(canonical.encode()).hexdigest(),
                   pares_verificados=True, label_propagation='pendiente',
                   semilla=system.config.semilla, pagerank_tol=1e-10, pagerank_max_iter=100)
    return dict(resumen=summary, nodos=nodes, aristas=edges,
                orden_nodos_analisis=list(analyzed.nodes()),
                comunidades=[dict(comunidad=c, productos=n) for c, n in sorted(counts.items())])


def collect_demo(data_dir, seed=2026, k=5, queries=5, repetitions=5, progress=print):
    """Reproduce todos los eventos del Parquet en una aplicación nueva, sin precarga."""
    if min(k, queries, repetitions) < 1:
        raise ValueError('k, consultas y repeticiones deben ser positivos')
    data_dir = Path(data_dir).resolve()
    if not (data_dir / 'events.parquet').is_file():
        raise FileNotFoundError(f'Falta {data_dir / "events.parquet"}; consultar README.md')
    config = Config(dir_datos=data_dir, precargar=False, semilla=seed,
                    reconstruir_cada_seg=float('inf'))
    app = create_app(config)
    controlled = controlled_scenes()
    records, payment_rows, evolution = [], [], []
    orders = defaultdict(set)
    source_types, origins, statuses = Counter(), Counter(), Counter()
    first_purchase = None
    source_rows = 0
    with TestClient(app) as client:
        q = partial(record_request, client, records)
        q('GET', '/salud')
        stream = iter(iter_events(data_dir / 'events.parquet'))
        progress('Reproduciendo events.parquet mediante /eventos/lote…')
        while batch := list(islice(stream, 250)):
            response = client.post('/eventos/lote', json=batch)
            response.raise_for_status()
            answers = response.json()['resultados']
            for event, answer in zip(batch, answers, strict=True):
                source_rows += 1
                source_types[event['event_type']] += 1
                origins[event.get('event_origin') or 'sin_origen'] += 1
                statuses[answer['estado']] += 1
                if answer['estado'] == 'aceptado':
                    if event['event_type'] == 'purchase':
                        orders[event['order_id']].add(str(event['product_id']))
                        first_purchase = first_purchase or event
                    if event['event_type'] == 'payment_attempt' and len(payment_rows) < 30:
                        fraud = answer['resultados']['fraude']
                        payment_rows.extend(dict(event_id=event['event_id'], clave=key,
                                                 decision=fraud['decision'], **value)
                                            for key, value in fraud['intensidad'].items())
            if source_rows % 1000 == 0:
                graph = app.state.sistema.cocompra.grafo
                evolution.append(dict(eventos_leidos=source_rows,
                                      eventos_aceptados=app.state.sistema.ingesta.aceptados,
                                      V=len(graph.adj), E=graph.number_of_edges(),
                                      peso_total=graph.total_weight()))
        if not first_purchase:
            raise ValueError('La demo requiere al menos una compra aceptada; usar una preparación con compras')
        system = app.state.sistema
        graph = system.cocompra.grafo
        final = dict(eventos_leidos=source_rows, eventos_aceptados=system.ingesta.aceptados,
                     V=len(graph.adj), E=graph.number_of_edges(), peso_total=graph.total_weight())
        if not evolution or evolution[-1]['eventos_leidos'] != source_rows:
            evolution.append(final)
        q('POST', '/admin/reconstruir')
        pid = first_purchase['product_id']
        uid = first_purchase['user_id']
        product = q('GET', f'/productos/{pid}')
        term = product['brand'] or (product['category_code'] or '').split('.')[-1]
        term = term or product['nombre'].split()[0]
        q('GET', '/buscar/autocompletar', params={'prefijo': term[:2], 'k': k})
        search = q('GET', '/buscar', params={'q': term, 'k': k})
        prices = q('GET', '/productos', params={'precio_min': 0,
                     'precio_max': float(product['price'] or 0), 'limite': k})
        api_neighbors = {method: q('GET', f'/productos/{pid}/similares',
                                  params={'metodo': method, 'k': k})
                         for method in ('knn', 'hnsw', 'minhash')}
        complements = q('GET', f'/productos/{pid}/complementarios', params={'k': k})
        recommendations = q('GET', f'/usuarios/{uid}/recomendaciones', params={'k': k})
        q('GET', '/cocompra/pares', params={'k': 10})
        q('GET', '/cocompra/influyentes', params={'k': 10})
        q('GET', '/cocompra/comunidades', params={'min_tamano': 1, 'limite': 500})
        q('GET', '/fraude/estadisticas')
        panel = q('GET', '/panel')
        # Idempotencia: el reenvío no cambia ventas ni las relaciones del grafo.
        before = (graph.number_of_edges(), graph.total_weight(), panel['ventas'])
        repeated = q('POST', '/eventos', json=first_purchase)
        after = (graph.number_of_edges(), graph.total_weight(), q('GET', '/panel')['ventas'])
        if repeated['estado'] != 'duplicado' or before != after:
            raise AssertionError('El reenvío modificó ventas o el grafo')
        progress('Comparando índices con referencias exactas y exportando el grafo completo…')
        timings, neighbors, set_neighbors = similarity_measurements(
            system.recomendacion, seed, k, queries, repetitions)
        snapshot = graph_snapshot(system, orders)
        stats = q('GET', '/admin/estadisticas')

    root = Path(__file__).resolve().parents[2]
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True)
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=root, capture_output=True, text=True)
    code_paths = [*sorted((root / 'src/analysis').glob('*.py')), root / 'scripts/demo_tecnica.py',
                  *sorted((root / 'src/structures').glob('*.py')),
                  *sorted((root / 'API_SERVICIOS').rglob('*.py'))]
    inputs = {p.name: digest_file(p) for p in sorted(data_dir.glob('*.parquet'))}
    if (data_dir / 'manifest.json').exists():
        inputs['manifest.json'] = digest_file(data_dir / 'manifest.json')
    settings = asdict(config)
    settings['dir_datos'] = str(data_dir)
    settings['reconstruir_cada_seg'] = 'infinito; reconstrucción explícita'
    return dict(metadata=dict(fecha_utc=datetime.now(timezone.utc).isoformat(),
                              plataforma=platform.platform(), python=platform.python_version(),
                              semilla=seed, k=k, consultas=queries, repeticiones_consulta=repetitions,
                              datos=str(data_dir), archivos_sha256=inputs,
                              codigo_sha256={str(p.relative_to(root)): digest_file(p) for p in code_paths},
                              git_revision=revision.stdout.strip(), git_con_cambios=bool(dirty.stdout.strip()),
                              pythonhashseed=os.environ.get('PYTHONHASHSEED', 'aleatorio al iniciar Python'),
                              dependencias={name: version(name) for name in ('fastapi', 'httpx', 'pyarrow')},
                              configuracion=settings, transporte='HTTP ASGI en proceso mediante TestClient',
                              alcance='demo piloto; índices fijos; repeticiones de consultas, no construcciones'),
                fuente=dict(filas=source_rows, tipos=dict(source_types), origenes=dict(origins),
                            estados=dict(statuses)), control=controlled, consultas=records,
                evolucion_grafo=evolution, grafo=snapshot, mediciones=timings,
                vecinos=neighbors, vecinos_conjuntos=set_neighbors, pagos_historico=payment_rows,
                servicio=dict(product_id=pid, user_id=uid, termino=term, producto=product,
                              busqueda=search, rango=prices, similares=api_neighbors,
                              complementarios=complements, recomendaciones=recommendations, panel=panel),
                estadisticas=stats, idempotencia_verificada=True)


def save_evidence(evidence, output):
    output = Path(output)
    # Una carpeta por corrida evita mezclar figuras antiguas con resultados nuevos.
    output.mkdir(parents=True, exist_ok=False)
    (output / 'evidencia.json').write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    (output / 'escenario_prioridades.json').write_text(
        json.dumps(list(reversed(evidence['control']['eventos'])), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return output
