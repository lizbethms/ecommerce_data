"""Medición aislada de memoria para estructuras de detección de pagos."""
from collections import Counter
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import tracemalloc

import pyarrow.parquet as pq

from src.structures.bloom import BloomFilter
from src.structures.count_min import CountMinSketch, WindowedCMS
from src.structures.hnsw import HNSW
from src.structures.kd_tree import KDTree, squared_distance
from src.structures.minhash_lsh import LSHIndex, MinHash, jaccard
from src.data.parquet_io import iter_rows
from API_SERVICIOS.servicios.recomendacion import ServicioRecomendacion


CASOS = ('bloom', 'set_exacto', 'cms', 'counter_exacto', 'cms_ventanas', 'counter_ventanas',
         'hnsw', 'kd_tree', 'fuerza_bruta_vectores', 'minhash_lsh', 'jaccard_exhaustivo')
PARES = (('bloom', 'set_exacto'), ('cms', 'counter_exacto'),
         ('cms_ventanas', 'counter_ventanas'), ('hnsw', 'kd_tree'),
         ('hnsw', 'fuerza_bruta_vectores'), ('minhash_lsh', 'jaccard_exhaustivo'))
PAGOS = set(CASOS[:6])
VECTORES = {'hnsw', 'kd_tree', 'fuerza_bruta_vectores'}


def workload(path):
    """Carga solo columnas de pago; conserva el mismo input para cada caso."""
    parquet = pq.ParquetFile(path)
    entries = []
    digest = hashlib.sha256()
    payments = 0
    columns = ['event_type', 'event_time', 'user_id', 'device_id', 'payment_method_id']
    for batch in parquet.iter_batches(batch_size=8192, columns=columns):
        for row in batch.to_pylist():
            if row['event_type'] != 'payment_attempt':
                continue
            payments += 1
            ts = row['event_time'].astimezone(timezone.utc).timestamp()
            for kind, field in (('account', 'user_id'), ('device', 'device_id'),
                                ('payment_method', 'payment_method_id')):
                if row[field]:
                    key = f'{kind}:{row[field]}'
                    entries.append((key, ts))
                    digest.update(key.encode('utf-8') + b'\0' + repr(ts).encode() + b'\n')
    manifest_path = Path(path).parent / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    unique = sorted({key for key, _ in entries})
    return entries, unique, dict(
        eventos_archivo=parquet.metadata.num_rows, pagos=payments,
        actualizaciones=len(entries), claves_unicas=len(unique),
        unidad='claves', n_indice=len(unique),
        workload_sha256=digest.hexdigest(), semilla_datos=manifest.get('seed'),
        generacion_id=manifest.get('generation_run_id'))


def vector_workload(path):
    """Vectores de 19 dimensiones derivados del catálogo, sin popularidad dinámica."""
    directory = Path(path).parent
    products = list(iter_rows(directory / 'catalog.parquet'))
    prices = [float(row['last_observed_price'] or 0) for row in products]
    max_log = math.log1p(max(prices, default=0))
    vectors = {}
    for row in products:
        product = dict(product_id=row['product_id'], price=row['last_observed_price'],
                       category_code=row['category_code'], category_id=row['category_id'],
                       brand=row['brand'], popularidad=0, vendidos=0, vistas=0)
        vectors[product['product_id']] = ServicioRecomendacion.vector(None, product, max_log, 0)
    digest = hashlib.sha256()
    for key, vector in sorted(vectors.items()):
        digest.update(repr((key, vector)).encode() + b'\n')
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    return vectors, sorted(vectors), dict(eventos_archivo=pq.ParquetFile(path).metadata.num_rows,
                                          pagos=None, actualizaciones=None, claves_unicas=None,
                                          unidad='vectores', n_indice=len(vectors),
                                          workload_sha256=digest.hexdigest(),
                                          semilla_datos=manifest.get('seed'),
                                          generacion_id=manifest.get('generation_run_id'))


def set_workload(path):
    """Conjuntos de compradores/visitantes por producto para una comparación fija."""
    parquet = pq.ParquetFile(path)
    sets = {}
    for batch in parquet.iter_batches(batch_size=8192,
                                      columns=['event_type', 'user_id', 'product_id']):
        for row in batch.to_pylist():
            if row['event_type'] in {'view', 'cart', 'purchase'} and row['user_id'] and row['product_id']:
                sets.setdefault(row['product_id'], set()).add(row['user_id'])
    digest = hashlib.sha256()
    for key, users in sorted(sets.items()):
        digest.update(key.encode() + b'\0')
        for user in sorted(users):
            digest.update(user.encode() + b'\0')
    manifest_path = Path(path).parent / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    return sets, sorted(sets), dict(eventos_archivo=parquet.metadata.num_rows,
                                    pagos=None, actualizaciones=None, claves_unicas=None,
                                    unidad='conjuntos', n_indice=len(sets),
                                    workload_sha256=digest.hexdigest(),
                                    semilla_datos=manifest.get('seed'),
                                    generacion_id=manifest.get('generation_run_id'))


def max_rss_bytes():
    """Pico del proceso completo, no pico incremental de una fase."""
    try:
        import resource
    except ImportError:
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == 'darwin' else value * 1024


class CounterVentanas:
    """Referencia exacta con los mismos bloques temporales de WindowedCMS."""
    def __init__(self, window=600, slots=6):
        self.window, self.slots = window, slots
        self.buckets = {}

    def add(self, key, ts):
        slot = int(ts // (self.window / self.slots))
        for old in [s for s in self.buckets if s <= slot - self.slots]:
            del self.buckets[old]
        if slot <= max(self.buckets, default=slot) - self.slots:
            return
        self.buckets.setdefault(slot, Counter())[key] += 1

    def estimate(self, key, ts):
        slot = int(ts // (self.window / self.slots))
        return sum(counts[key] for s, counts in self.buckets.items()
                   if slot - self.slots < s <= slot)


def build(case, entries, unique):
    if case == 'bloom':
        index = BloomFilter(max(1, len(unique)), .01)
        index.update(unique)
    elif case == 'set_exacto':
        index = set(unique)
    elif case == 'cms':
        index = CountMinSketch(1024, 4)
        for key, _ in entries:
            index.add(key)
    elif case == 'counter_exacto':
        index = Counter(key for key, _ in entries)
    elif case == 'cms_ventanas':
        index = WindowedCMS(600, 6, 1024, 4)
        for key, ts in entries:
            index.add(key, ts)
    elif case == 'counter_ventanas':
        index = CounterVentanas(600, 6)
        for key, ts in entries:
            index.add(key, ts)
    elif case == 'kd_tree':
        index = KDTree(entries.items())
    elif case == 'hnsw':
        index = HNSW(8, 48, 48, 2026)
        for key, vector in entries.items():
            index.insert(key, vector)
    elif case == 'fuerza_bruta_vectores':
        index = dict(entries)
    elif case == 'minhash_lsh':
        minhash = MinHash(64, 2026)
        lsh = LSHIndex(16, 4)
        for key, users in entries.items():
            lsh.insert(key, minhash.signature(users))
        index = (minhash, lsh)
    elif case == 'jaccard_exhaustivo':
        index = dict(entries)
    else:
        raise ValueError(f'Caso desconocido: {case}')
    return index


def query(index, case, entries, unique):
    # Una muestra fija evita que el resultado de la consulta quede residente.
    if case in ('bloom', 'set_exacto'):
        return sum(key in index for key in unique[:1000])
    if case in ('cms', 'counter_exacto'):
        return sum(index.estimate(key) if case == 'cms' else index[key]
                   for key in unique[:1000])
    if case in VECTORES:
        if not unique:
            return 0
        key = unique[0]
        vector = entries[key]
        if case == 'hnsw':
            return len(index.search(vector, 5, exclude=key))
        if case == 'kd_tree':
            return len(index.knn(vector, 5, exclude=key))
        return len(sorted((squared_distance(vector, other), other_key)
                          for other_key, other in index.items() if other_key != key)[:5])
    if case == 'minhash_lsh':
        return len(index[1].query(unique[0], 5)) if unique else 0
    if case == 'jaccard_exhaustivo':
        if not unique:
            return 0
        key = unique[0]
        return len(sorted(((jaccard(index[key], users), other)
                           for other, users in index.items() if other != key), reverse=True)[:5])
    if not entries:
        return 0
    ts = entries[-1][1]
    return sum(index.estimate(key, ts) for key in unique[:1000])


def measure(path, case, repetition):
    if case in PAGOS:
        entries, unique, info = workload(path)
        if case not in ('bloom', 'set_exacto'):
            info['unidad'] = 'actualizaciones'
            info['n_indice'] = info['actualizaciones']
    elif case in VECTORES:
        entries, unique, info = vector_workload(path)
    else:
        entries, unique, info = set_workload(path)
    # El input está cargado antes de iniciar el trazado: se mide el índice incremental.
    gc.collect()
    tracemalloc.start()
    baseline, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    index = build(case, entries, unique)
    gc.collect()
    resident, peak_build = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    before_query, _ = tracemalloc.get_traced_memory()
    query(index, case, entries, unique)
    _, peak_query = tracemalloc.get_traced_memory()
    result = dict(escala=Path(path).parent.name, caso=case, repeticion=repetition,
                  estado='completado', **info,
                  actual_indice_bytes=max(0, resident - baseline),
                  pico_construccion_bytes=max(0, peak_build - baseline),
                  pico_adicional_consulta_bytes=max(0, peak_query - before_query),
                  pico_rss_proceso_bytes=max_rss_bytes(),
                  plataforma=platform.platform(), python=platform.python_version(),
                  parametros=dict(fp_rate=.01, cms_width=1024, cms_depth=4,
                                  ventana_seg=600, subventanas=6, hnsw_m=8,
                                  hnsw_ef=48, minhash_permutaciones=64, lsh_bandas=16))
    tracemalloc.stop()
    return result


def summary_rows(rows):
    groups = {}
    for row in rows:
        if row['estado'] == 'completado':
            groups.setdefault((row['eventos_archivo'], row['caso']), []).append(row)
    result = []
    fields = ('actual_indice_bytes', 'pico_construccion_bytes',
              'pico_adicional_consulta_bytes', 'pico_rss_proceso_bytes')
    for (events, case), group in sorted(groups.items()):
        if len({row['workload_sha256'] for row in group}) != 1:
            raise ValueError(f'Entradas distintas entre repeticiones: {events} {case}')
        first = group[0]
        item = dict(eventos_archivo=events, escala=first['escala'], caso=case,
                    pagos=first['pagos'], actualizaciones=first['actualizaciones'],
                    claves_unicas=first['claves_unicas'],
                    unidad=first.get('unidad', 'claves' if case in ('bloom', 'set_exacto')
                                    else 'actualizaciones'),
                    n_indice=first.get('n_indice', first['claves_unicas'] if case in
                                       ('bloom', 'set_exacto') else first['actualizaciones']),
                    repeticiones=len(group))
        for field in fields:
            values = [r[field] for r in group if r[field] is not None]
            item[field + '_media'] = statistics.mean(values) if values else None
            item[field + '_desviacion'] = statistics.stdev(values) if len(values) > 1 else None
        result.append(item)
    return result


def save_evidence(path, rows, sources=None):
    Path(path).write_text(json.dumps(dict(version=1, fecha_utc=datetime.now(timezone.utc).isoformat(),
                                         alcance='Memoria de índices de claves de pagos; input excluido de tracemalloc',
                                         fuentes=sources or [], filas=rows),
                                     ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
