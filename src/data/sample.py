"""Copia pequeña del CSV por sesiones completas, con más peso a las compras.

Dos pasadas sobre una ventana inicial de la fuente: la primera resume cada
sesión y la segunda copia, en el orden original, las filas de las sesiones
elegidas. Así se conservan el orden temporal y la cabecera REES46.
"""
import csv
import json
import random
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from .schema import SOURCE_COLUMNS


def _parse(value):
    return datetime.fromisoformat(value.replace(' UTC', '+00:00'))


def sample_sessions(source, output_csv, target_rows=5000, window_rows=1_000_000,
                    seed=2026, max_session_rows=60, purchase_share=0.6, guard_minutes=30):
    source, output_csv = Path(source).resolve(), Path(output_csv).resolve()
    if target_rows <= 0 or window_rows < target_rows:
        raise ValueError('Se requiere 0 < target_rows <= window_rows')
    if output_csv == source:
        raise ValueError('La copia no puede sobrescribir la fuente')
    sessions = {}
    last_time = None
    rows_read = 0
    with source.open(newline='', encoding='utf-8') as stream:
        reader = csv.reader(stream)
        if tuple(next(reader)) != SOURCE_COLUMNS:
            raise ValueError('Cabecera distinta al esquema REES46')
        for row in reader:
            if rows_read >= window_rows:
                break
            rows_read += 1
            if not row[8]:
                continue  # sesión ausente: no se puede garantizar una sesión completa
            key = (row[7], row[8])
            info = sessions.get(key)
            if info is None:
                info = sessions[key] = [0, set(), None]
            info[0] += 1
            info[2] = row[0]
            if row[1] == 'purchase':
                info[1].add(row[2])
            last_time = row[0]
    if last_time is None:
        raise ValueError('Fuente vacía')
    # Una sesión activa cerca del final de la ventana podría continuar fuera de ella.
    guard = (_parse(last_time) - timedelta(minutes=guard_minutes)).strftime('%Y-%m-%d %H:%M:%S UTC')
    strata = {'multi_purchase': [], 'single_purchase': [], 'browse': []}
    for key, (rows, bought, seen) in sessions.items():
        if rows > max_session_rows or seen >= guard:
            continue
        name = 'multi_purchase' if len(bought) >= 2 else 'single_purchase' if bought else 'browse'
        strata[name].append(key)
    rng = random.Random(seed)
    chosen, used, chosen_by_stratum = set(), 0, Counter()
    budgets = (('multi_purchase', purchase_share), ('single_purchase', purchase_share), ('browse', 1.0))
    for name, share in budgets:
        candidates = sorted(strata[name])
        rng.shuffle(candidates)
        limit = int(target_rows * share)
        for key in candidates:
            rows = sessions[key][0]
            if used + rows > limit:
                continue
            chosen.add(key)
            used += rows
            chosen_by_stratum[name] += 1
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    types = Counter()
    with source.open(newline='', encoding='utf-8') as stream, output_csv.open('x', newline='', encoding='utf-8') as out:
        reader = csv.reader(stream)
        writer = csv.writer(out, lineterminator='\n')
        writer.writerow(next(reader))
        for index, row in enumerate(reader):
            if index >= rows_read:
                break
            if (row[7], row[8]) in chosen:
                writer.writerow(row)
                types[row[1]] += 1
    return dict(rule='complete_sessions_from_chronological_window;purchase_sessions_weighted',
                source=str(source), output=str(output_csv), seed=seed,
                window_rows=rows_read, window_last_time=last_time, guard_minutes=guard_minutes,
                max_session_rows=max_session_rows, purchase_share=purchase_share,
                target_rows=target_rows, rows_written=sum(types.values()), by_type=dict(types),
                sessions_available={k: len(v) for k, v in strata.items()},
                sessions_chosen=dict(chosen_by_stratum))


def write_manifest(info, path, source_sha256):
    info = dict(info, source_sha256=source_sha256)
    Path(path).write_text(json.dumps(info, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return info
