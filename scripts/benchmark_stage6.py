#!/usr/bin/env python3
"""Microbenchmarks en memoria; no confundir eventos, claves y tamaño residente."""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import random
import statistics
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.structures.probabilistic import BloomFilter, CountMinSketch


def summary(samples):
    return dict(media=statistics.mean(samples), desviacion=statistics.stdev(samples) if len(samples) > 1 else 0,
                repeticiones=len(samples))


def measure(factory, update, query, updates, queries, repeats):
    construction, updates_times, queries_times = [], [], []
    answers = None
    for _ in range(repeats):
        start = time.perf_counter()
        structure = factory()
        constructed = time.perf_counter()
        for key in updates:
            update(structure, key)
        updated = time.perf_counter()
        answers = [query(structure, key) for key in queries]
        queried = time.perf_counter()
        construction.append(constructed - start)
        updates_times.append(updated - constructed)
        queries_times.append(queried - updated)
    # Memoria en pasada separada para no distorsionar las mediciones de tiempo.
    tracemalloc.start()
    structure = factory()
    for key in updates:
        update(structure, key)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return dict(construccion_segundos=summary(construction), actualizaciones_segundos=summary(updates_times),
                consultas_segundos=summary(queries_times), memoria_actual_bytes=current, memoria_pico_bytes=peak), answers


def benchmark(size, repeats):
    rng = random.Random(2026)
    members = [f'device:{i}' for i in range(size)]
    absent = [f'absent:{i}' for i in range(size)]
    bloom_queries = members + absent
    bloom, answers = measure(lambda: BloomFilter(size), lambda s, k: s.add(k), lambda s, k: s.contains(k),
                             members, bloom_queries, repeats)
    exact_set, truth = measure(set, lambda s, k: s.add(k), lambda s, k: k in s, members, bloom_queries, repeats)
    bloom.update(claves_insertadas=size, consultas_ausentes=size,
                 falsos_positivos=sum(answers[size:]), tasa_falsos_positivos=sum(answers[size:]) / size,
                 falsos_negativos=sum(not value for value in answers[:size]))
    cardinality = max(2, size // 20)
    updates = ['device:hot' if rng.random() < .3 else f'device:{rng.randrange(cardinality)}' for _ in range(size)]
    queries = sorted(set(updates)) + ['absent']
    cms, estimates = measure(CountMinSketch, lambda s, k: s.add(k), lambda s, k: s.estimate(k), updates, queries, repeats)
    exact_counts, counts = measure(Counter, lambda s, k: s.update([k]), lambda s, k: s[k], updates, queries, repeats)
    errors = [estimate - count for estimate, count in zip(estimates, counts)]
    cms.update(actualizaciones=size, claves_distintas=len(set(updates)), epsilon=.01, delta=.001,
               error_medio=statistics.mean(errors), error_maximo=max(errors), subestimaciones=sum(error < 0 for error in errors))
    return dict(escala=size, bloom=bloom, conjunto_exacto=exact_set, cms=cms, diccionario_exacto=exact_counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repetitions', type=int, default=100)
    args = parser.parse_args()
    if args.output.exists() or args.repetitions <= 0:
        parser.error('Salida nueva y repeticiones positivas requeridas')
    result = dict(semilla=2026, python=platform.python_version(), plataforma=platform.platform(),
                  procesador=platform.processor(), nucleos=__import__('os').cpu_count(),
                  dependencias={name: importlib.metadata.version(name) for name in ('fastapi', 'uvicorn', 'httpx')},
                  codigo_sha256=hashlib.sha256((ROOT / 'src/structures/probabilistic.py').read_bytes()).hexdigest(),
                  protocolo='Estado nuevo por repetición; sin generación, HTTP, CSV ni tracemalloc en tiempos. Memoria incremental Python excluye claves de entrada compartidas. CMS individual, no anillo completo.',
                  resultados=[benchmark(size, args.repetitions) for size in (1000, 10000)])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'salida': str(args.output), 'repeticiones': args.repetitions}))


if __name__ == '__main__':
    main()
