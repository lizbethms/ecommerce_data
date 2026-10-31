"""Tiempos de construcción y de operación por estructura y escala; calidad de Bloom y CMS.

Cada caso se mide en un proceso nuevo (scripts/benchmark_tiempos.py). Las entradas se
cargan antes de cronometrar, así que solo se mide la estructura. La construcción es la
operación cara y se repite pocas veces; la operación típica se repite --repeticiones
veces sobre un lote fijo de consultas y se reporta por operación.
"""
import asyncio
from collections import Counter
from datetime import datetime, timezone
import gc
import json
import math
from pathlib import Path
import random
import statistics
import time

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from API_SERVICIOS.config import Config
from API_SERVICIOS.servicios.busqueda import terminos
from API_SERVICIOS.servicios.catalogo import ServicioCatalogo
from src.analysis.memoria import CounterVentanas, set_workload, vector_workload, workload
from src.analysis.plataforma import plataforma
from src.data.parquet_io import iter_rows
from src.structures.bloom import BloomFilter
from src.structures.bplus_tree import BPlusTree
from src.structures.count_min import CountMinSketch, WindowedCMS
from src.structures.fifo import BoundedFIFO
from src.structures.graph import WeightedGraph
from src.structures.hash_table import HashTable
from src.structures.heap import MinHeap
from src.structures.hnsw import HNSW
from src.structures.kd_tree import KDTree
from src.structures.lru import LRUCache
from src.structures.minhash_lsh import LSHIndex, MinHash
from src.structures.sorting import merge_sort
from src.structures.sparse_matrix import SparseMatrix
from src.structures.topk import top_k
from src.structures.trie import Trie

CONFIG = Config(dir_datos=None)
LOTE_CONSULTAS = 1000
CONSULTAS_COSTOSAS = 5  # KD-Tree, HNSW y LSH: pocas consultas, cada una repetida
AUSENTES_BLOOM = 100_000

# carga: qué entrada usa; n: qué se cuenta; construcción y operación con su complejidad esperada
# y la pendiente aproximada en log-log (tiempo frente a n) para contrastar con lo observado.
CASOS = {
    'fifo': dict(carga='eventos', n='eventos', construccion='O(n)', pendiente_construccion=1.0,
                 operacion=None, nota='put + get por evento con contrapresión'),
    'merge_sort': dict(carga='eventos', n='eventos', construccion='O(n log n)', pendiente_construccion=1.0,
                       operacion=None, nota='orden por (tiempo, event_id)'),
    'hash_table': dict(carga='eventos', n='eventos', construccion='O(n) esperado', pendiente_construccion=1.0,
                       operacion='get: O(1) esperado', pendiente_operacion=0.0),
    'heap': dict(carga='ordenes', n='órdenes', construccion='O(n log n)', pendiente_construccion=1.0,
                 operacion='pushpop: O(log n)', pendiente_operacion=0.0),
    'lru': dict(carga='accesos', n='accesos a productos', construccion='O(n)', pendiente_construccion=1.0,
                operacion='get: O(1)', pendiente_operacion=0.0, nota=f'capacidad {CONFIG.lru_capacidad}'),
    'sparse_matrix': dict(carga='interacciones', n='interacciones', construccion='O(n)', pendiente_construccion=1.0,
                          operacion='get: O(1) esperado', pendiente_operacion=0.0),
    'bplus_tree': dict(carga='catalogo', n='productos', construccion='O(n log n)', pendiente_construccion=1.0,
                       operacion='search: O(log n)', pendiente_operacion=0.0, nota=f'orden {CONFIG.orden_bplus}'),
    'kd_tree': dict(carga='vectores', n='vectores', construccion='O(n log² n)', pendiente_construccion=1.0,
                    operacion='knn k=5: O(log n) a O(n) en 19 dimensiones', pendiente_operacion=None),
    'trie': dict(carga='catalogo', n='productos', construccion='O(total de caracteres)', pendiente_construccion=1.0,
                 operacion='complete: O(prefijo + subárbol)', pendiente_operacion=None),
    'top_k': dict(carga='catalogo', n='productos', construccion=None,
                  operacion='top_k k=10: O(n log k)', pendiente_operacion=1.0),
    'bloom': dict(carga='pagos', n='claves únicas', construccion='O(n·k)', pendiente_construccion=1.0,
                  operacion='pertenencia: O(k)', pendiente_operacion=0.0),
    'set_exacto': dict(carga='pagos', n='claves únicas', construccion='O(n) esperado', pendiente_construccion=1.0,
                       operacion='pertenencia: O(1) esperado', pendiente_operacion=0.0),
    'cms': dict(carga='pagos', n='actualizaciones', construccion='O(n·d)', pendiente_construccion=1.0,
                operacion='estimate: O(d)', pendiente_operacion=0.0),
    'counter_exacto': dict(carga='pagos', n='actualizaciones', construccion='O(n) esperado', pendiente_construccion=1.0,
                           operacion='lookup: O(1) esperado', pendiente_operacion=0.0),
    'cms_ventanas': dict(carga='pagos', n='actualizaciones', construccion='O(n·d)', pendiente_construccion=1.0,
                         operacion='estimate: O(d·subventanas)', pendiente_operacion=0.0),
    'counter_ventanas': dict(carga='pagos', n='actualizaciones', construccion='O(n) esperado',
                             pendiente_construccion=1.0, operacion='estimate: O(subventanas)', pendiente_operacion=0.0),
    'hnsw': dict(carga='vectores', n='vectores', construccion='O(n log n) aprox.', pendiente_construccion=1.0,
                 operacion='search k=5: O(log n) aprox.', pendiente_operacion=0.0),
    'minhash_lsh': dict(carga='conjuntos', n='conjuntos', construccion='O(Σ|conjunto|·permutaciones)',
                        pendiente_construccion=1.0, operacion='query k=5: O(bandas + candidatos)',
                        pendiente_operacion=None),
    'grafo': dict(carga='compras', n='compras', construccion='O(Σ productos por orden²)', pendiente_construccion=1.0,
                  operacion=None, nota='grafo de co-compra como en ServicioCoCompra'),
}
# Comparaciones probabilística frente a exacta (E3): mismo input dentro de cada par.
PARES = (('bloom', 'set_exacto'), ('cms', 'counter_exacto'), ('cms_ventanas', 'counter_ventanas'))


def _columns(path, names):
    """Columnas como listas de Python; los tiempos pasan a segundos epoch sin crear datetime."""
    table = pq.read_table(path, columns=names)
    result = {}
    for name in names:
        column = table.column(name)
        if pa.types.is_timestamp(column.type):
            factor = {'s': 1, 'ms': 1e3, 'us': 1e6, 'ns': 1e9}[column.type.unit]
            column = pc.divide(pc.cast(column, pa.int64()).cast(pa.float64()), factor)
        result[name] = column.to_pylist()
    return result


def _eventos(path):
    c = _columns(path, ['event_time', 'event_id'])
    return list(zip(c['event_time'], c['event_id']))


def _ordenes(path):
    """Plazo de cada orden con la misma regla de ServicioPriorizacion (primera compra de la orden)."""
    c = _columns(path, ['event_type', 'event_time', 'order_id', 'delivery_type', 'scheduled_at'])
    horas = {'express': CONFIG.plazo_express_h}
    plazos = {}
    for tipo, ts, orden, entrega, programada in zip(*c.values()):
        if tipo != 'purchase' or not orden or orden in plazos:
            continue
        if entrega == 'scheduled' and programada:
            plazos[orden] = programada
        else:
            plazos[orden] = ts + horas.get(entrega, CONFIG.plazo_standard_h) * 3600
    return [((1, plazo), orden) for orden, plazo in plazos.items()]


def _accesos(path):
    return [p for p in _columns(path, ['product_id'])['product_id'] if p]


def _interacciones(path):
    c = _columns(path, ['event_type', 'user_id', 'product_id', 'rating'])
    salida = []
    for tipo, usuario, producto, rating in zip(*c.values()):
        peso = CONFIG.pesos_interaccion.get(tipo, 0.0)
        if tipo == 'review' and rating is not None:
            peso *= rating - 3
        if peso and usuario and producto:
            salida.append((usuario, producto, peso))
    return salida


def _catalogo(path):
    """Productos tal como los registra ServicioCatalogo (nombre y términos de búsqueda incluidos)."""
    catalogo = ServicioCatalogo(CONFIG)
    catalogo.cargar_catalogo(iter_rows(Path(path).parent / 'catalog.parquet'))
    productos = []
    for pid in catalogo.ids():
        registro = catalogo.registro(pid)
        productos.append(dict(product_id=pid, precio=float(registro['price'] or 0),
                              terminos=sorted(terminos(registro))))
    return productos


def _compras(path):
    c = _columns(path, ['event_type', 'order_id', 'product_id'])
    return [(o, p) for t, o, p in zip(*c.values()) if t == 'purchase' and o and p]


def cargar(case, path):
    """Entrada del caso y su tamaño n (la carga real de la estructura, no el número de eventos)."""
    carga = CASOS[case]['carga']
    if carga == 'pagos':
        entries, unique, _ = workload(path)
        n = len(unique) if case in ('bloom', 'set_exacto') else len(entries)
        return dict(entries=entries, unique=unique), n
    if carga == 'vectores':
        vectors, keys, _ = vector_workload(path)
        return dict(vectors=vectors, keys=keys), len(vectors)
    if carga == 'conjuntos':
        sets, keys, _ = set_workload(path)
        return dict(sets=sets, keys=keys), len(sets)
    loader = dict(eventos=_eventos, ordenes=_ordenes, accesos=_accesos, interacciones=_interacciones,
                  catalogo=_catalogo, compras=_compras)[carga]
    items = loader(path)
    return dict(items=items), len(items)


_LOOP = None


def _fifo(items):
    """Un solo event loop por proceso: crearlo en cada construcción mediría asyncio, no la FIFO."""
    global _LOOP
    if _LOOP is None:
        _LOOP = asyncio.new_event_loop()

    async def correr():
        fifo = BoundedFIFO(1024)
        for item in items:
            await fifo.put(item)
            fifo.get_nowait()
            fifo.task_done()
        return fifo
    return _LOOP.run_until_complete(correr())


def _lru(items):
    cache = LRUCache(CONFIG.lru_capacidad)
    for producto in items:
        if cache.get(producto) is None:
            cache.put(producto, True)
    return cache


def _grafo(items):
    grafo, por_orden = WeightedGraph(), {}
    for orden, producto in items:
        productos = por_orden.setdefault(orden, set())
        if producto in productos:
            continue
        grafo.add_node(producto)
        for otro in productos:
            grafo.add_edge(producto, otro, 1)
        productos.add(producto)
    return grafo


def _construir(case, data):
    items = data.get('items')
    if case == 'fifo':
        return _fifo(items)
    if case == 'merge_sort':
        return merge_sort(items)
    if case == 'hash_table':
        tabla = HashTable()
        for i, (_, event_id) in enumerate(items):
            tabla[event_id] = i
        return tabla
    if case == 'heap':
        heap = MinHeap()
        for clave, orden in items:
            heap.push(clave, orden)
        return heap
    if case == 'lru':
        return _lru(items)
    if case == 'sparse_matrix':
        matriz = SparseMatrix()
        for usuario, producto, peso in items:
            matriz.add(usuario, producto, peso)
        return matriz
    if case == 'bplus_tree':
        arbol = BPlusTree(CONFIG.orden_bplus)
        for producto in items:
            arbol.insert(producto['precio'], producto['product_id'])
        return arbol
    if case == 'trie':
        trie = Trie()
        for producto in items:
            for termino, tipo in producto['terminos']:
                trie.insert(termino.lower(), 0.0, producto['product_id'], tipo)
        return trie
    if case == 'top_k':
        return items
    if case == 'bloom':
        bloom = BloomFilter(max(1, len(data['unique'])), CONFIG.bloom_fp)
        bloom.update(data['unique'])
        return bloom
    if case == 'set_exacto':
        return set(data['unique'])
    if case == 'cms':
        cms = CountMinSketch(CONFIG.cms_ancho, CONFIG.cms_profundidad)
        for key, _ in data['entries']:
            cms.add(key)
        return cms
    if case == 'counter_exacto':
        return Counter(key for key, _ in data['entries'])
    if case == 'cms_ventanas':
        cms = WindowedCMS(CONFIG.ventana_fraude_seg, CONFIG.sub_ventanas, CONFIG.cms_ancho, CONFIG.cms_profundidad)
        for key, ts in data['entries']:
            cms.add(key, ts)
        return cms
    if case == 'counter_ventanas':
        contador = CounterVentanas(CONFIG.ventana_fraude_seg, CONFIG.sub_ventanas)
        for key, ts in data['entries']:
            contador.add(key, ts)
        return contador
    if case == 'kd_tree':
        return KDTree(data['vectors'].items())
    if case == 'hnsw':
        hnsw = HNSW(CONFIG.hnsw_m, CONFIG.hnsw_ef, CONFIG.hnsw_ef, CONFIG.semilla)
        for key, vector in data['vectors'].items():
            hnsw.insert(key, vector)
        return hnsw
    if case == 'minhash_lsh':
        minhash = MinHash(CONFIG.minhash_permutaciones, CONFIG.semilla)
        lsh = LSHIndex(CONFIG.lsh_bandas, CONFIG.minhash_permutaciones // CONFIG.lsh_bandas)
        for key, users in data['sets'].items():
            lsh.insert(key, minhash.signature(users))
        return lsh
    if case == 'grafo':
        return _grafo(items)
    raise ValueError(f'Caso desconocido: {case}')


def _lote(case, data, rng):
    """Consultas fijas, preparadas fuera de la medición; mitad presentes y mitad ausentes cuando aplica."""
    items = data.get('items')
    muestra = lambda pool, n: [pool[rng.randrange(len(pool))] for _ in range(n)] if pool else []
    if case == 'hash_table':
        return [e for _, e in muestra(items, LOTE_CONSULTAS // 2)] + [f'ausente:{i}' for i in range(LOTE_CONSULTAS // 2)]
    if case == 'heap':
        return [clave for clave, _ in muestra(items, LOTE_CONSULTAS)]
    if case == 'lru':
        return muestra(items, LOTE_CONSULTAS)
    if case == 'sparse_matrix':
        return [(u, p) for u, p, _ in muestra(items, LOTE_CONSULTAS)]
    if case == 'bplus_tree':
        return [p['precio'] for p in muestra(items, LOTE_CONSULTAS)]
    if case == 'trie':
        terminos_ = [t.lower() for p in items for t, _ in p['terminos'] if len(t) >= 2]
        return [t[:2] for t in muestra(terminos_, 100)]
    if case == 'top_k':
        return [None]
    if case in ('bloom', 'set_exacto'):
        return muestra(data['unique'], LOTE_CONSULTAS // 2) + [f'ausente:{i}' for i in range(LOTE_CONSULTAS // 2)]
    if case in ('cms', 'counter_exacto', 'cms_ventanas', 'counter_ventanas'):
        ultimo = data['entries'][-1][1] if data['entries'] else 0.0
        return [(key, ultimo) for key in muestra(data['unique'], LOTE_CONSULTAS)]
    if case in ('kd_tree', 'hnsw'):
        return muestra(data['keys'], CONSULTAS_COSTOSAS)
    if case == 'minhash_lsh':
        return muestra(data['keys'], CONSULTAS_COSTOSAS)
    return []


def _operar(case, index, lote, data):
    if case == 'hash_table':
        for key in lote:
            index.get(key)
    elif case == 'heap':
        for clave in lote:
            index.pushpop(clave, None)
    elif case == 'lru':
        for key in lote:
            index.get(key)
    elif case == 'sparse_matrix':
        for row, col in lote:
            index.get(row, col)
    elif case == 'bplus_tree':
        for key in lote:
            index.search(key)
    elif case == 'trie':
        for prefijo in lote:
            index.complete(prefijo, 10)
    elif case == 'top_k':
        top_k(index, 10, key=lambda p: p['precio'])
    elif case in ('bloom', 'set_exacto'):
        for key in lote:
            key in index
    elif case == 'cms':
        for key, _ in lote:
            index.estimate(key)
    elif case == 'counter_exacto':
        for key, _ in lote:
            index[key]
    elif case in ('cms_ventanas', 'counter_ventanas'):
        for key, ts in lote:
            index.estimate(key, ts)
    elif case == 'kd_tree':
        for key in lote:
            index.knn(data['vectors'][key], 5, exclude=key)
    elif case == 'hnsw':
        for key in lote:
            index.search(data['vectors'][key], 5, exclude=key)
    elif case == 'minhash_lsh':
        for key in lote:
            index.query(key, 5)


def _errores(estimados, exactos):
    diferencias = [e - x for e, x in zip(estimados, exactos)]
    if not diferencias:
        return dict(claves=0)
    return dict(claves=len(diferencias), mae=statistics.fmean(abs(d) for d in diferencias),
                rmse=math.sqrt(statistics.fmean(d * d for d in diferencias)),
                error_maximo=max(diferencias), error_minimo=min(diferencias),
                sobreestimadas=sum(1 for d in diferencias if d > 0) / len(diferencias))


def calidad(case, index, data):
    """E3: falsos positivos de Bloom y error de frecuencia de CMS sobre todas las claves reales."""
    if case == 'bloom':
        falsos_negativos = sum(1 for key in data['unique'] if key not in index)
        falsos_positivos = sum(1 for i in range(AUSENTES_BLOOM) if f'ausente:{i}' in index)
        return dict(bits=index.m, hashes=index.k, bytes=len(index.bits), insertadas=len(data['unique']),
                    falsos_negativos=falsos_negativos, ausentes_consultadas=AUSENTES_BLOOM,
                    fp_observada=falsos_positivos / AUSENTES_BLOOM, fp_objetivo=CONFIG.bloom_fp,
                    fp_teorica=index.expected_fp_rate())
    if case == 'cms':
        exacto = Counter(key for key, _ in data['entries'])
        claves = sorted(exacto)
        total = sum(exacto.values())
        epsilon = math.e / CONFIG.cms_ancho
        estimados = [index.estimate(k) for k in claves]
        cota = epsilon * total
        return dict(ancho=CONFIG.cms_ancho, profundidad=CONFIG.cms_profundidad, total_actualizaciones=total,
                    **_errores(estimados, [exacto[k] for k in claves]),
                    epsilon=epsilon, delta=math.exp(-CONFIG.cms_profundidad), cota_error=cota,
                    dentro_de_cota=(sum(1 for e, k in zip(estimados, claves) if e - exacto[k] <= cota) / len(claves)
                                    if claves else None))
    if case == 'cms_ventanas':
        if not data['entries']:
            return dict(claves=0)
        referencia = CounterVentanas(CONFIG.ventana_fraude_seg, CONFIG.sub_ventanas)
        for key, ts in data['entries']:
            referencia.add(key, ts)
        ultimo = data['entries'][-1][1]
        exactos = {k: referencia.estimate(k, ultimo) for k in data['unique']}
        activas = sorted(k for k, v in exactos.items() if v)
        estimados = {k: index.estimate(k, ultimo) for k in data['unique']}
        return dict(instante=ultimo, claves_activas=len(activas),
                    **_errores([estimados[k] for k in activas], [exactos[k] for k in activas]),
                    falsas_activas=sum(1 for k, v in exactos.items() if not v and estimados[k]))
    return None


def _resumen(muestras):
    if not muestras:
        return dict(media=None, desviacion=None, mediana=None, minimo=None, repeticiones=0)
    return dict(media=statistics.fmean(muestras), desviacion=statistics.stdev(muestras) if len(muestras) > 1 else None,
                mediana=statistics.median(muestras), minimo=min(muestras), repeticiones=len(muestras))


def measure(path, case, build_reps, op_reps, seed=2026):
    path = Path(path)
    spec = CASOS[case]
    data, n = cargar(case, path)
    if case == 'fifo':
        _fifo(data['items'][:10])  # calentamiento del event loop, fuera de la medición
    construcciones, index = [], None
    for _ in range(build_reps if spec['construccion'] else 1):
        index = None
        gc.collect()
        inicio = time.perf_counter_ns()
        index = _construir(case, data)
        construcciones.append((time.perf_counter_ns() - inicio) / 1e6)
    operaciones, tamano_lote = [], 0
    if spec['operacion']:
        lote = _lote(case, data, random.Random(seed))
        tamano_lote = len(lote)
        if lote:
            _operar(case, index, lote, data)  # calentamiento
            for _ in range(op_reps):
                inicio = time.perf_counter_ns()
                _operar(case, index, lote, data)
                operaciones.append((time.perf_counter_ns() - inicio) / 1e6 / len(lote))
    return dict(escala=path.parent.name, caso=case, estado='completado', n=n, unidad=spec['n'],
                eventos_archivo=pq.ParquetFile(path).metadata.num_rows,
                complejidad_construccion=spec['construccion'], complejidad_operacion=spec['operacion'],
                pendiente_esperada_construccion=spec.get('pendiente_construccion'),
                pendiente_esperada_operacion=spec.get('pendiente_operacion'), nota=spec.get('nota'),
                construccion_ms=_resumen(construcciones if spec['construccion'] else []),
                construccion_muestras_ms=construcciones if spec['construccion'] else [],
                operacion_ms=_resumen(operaciones), operaciones_por_repeticion=tamano_lote,
                calidad=calidad(case, index, data), semilla=seed, plataforma=plataforma())


def save_evidence(path, rows, sources, parameters):
    Path(path).write_text(json.dumps(dict(version=1, fecha_utc=datetime.now(timezone.utc).isoformat(),
                                          alcance='Tiempos de estructuras con entradas precargadas; un proceso por caso',
                                          parametros=parameters, fuentes=sources, filas=rows),
                                     ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
