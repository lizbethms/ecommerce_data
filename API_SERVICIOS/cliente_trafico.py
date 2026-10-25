"""Reproduce events.parquet contra la API en lotes, con tasa objetivo.

    python -m API_SERVICIOS.cliente_trafico --tasa 2000 --lote 200
    python -m API_SERVICIOS.cliente_trafico --limite 3000 --reenvios 0.02 --invalidos 0.01

Puede inyectar reenvíos (mismo event_id y contenido) y eventos inválidos
para ver los rechazos y la deduplicación en la respuesta.
"""
import argparse
import random
import time
from collections import Counter

import httpx

from . import RAIZ
from src.data.parquet_io import iter_events

INVALIDOS = (
    lambda e: dict(e, event_type='teleport'),
    lambda e: dict(e, event_time='ayer por la tarde'),
    lambda e: dict(e, price='-3.50'),
    lambda e: dict(e, user_id=None),
)


def lotes(ruta, tamano, limite, reenvios, invalidos, rng):
    lote, enviados = [], 0
    for evento in iter_events(ruta):
        if limite and enviados >= limite:
            break
        lote.append(evento)
        if rng.random() < reenvios:
            lote.append(dict(evento))
        if rng.random() < invalidos:
            lote.append(dict(rng.choice(INVALIDOS)(evento), event_id=f'invalido:{enviados}'))
        enviados += 1
        if len(lote) >= tamano:
            yield lote
            lote = []
    if lote:
        yield lote


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--eventos', default=str(RAIZ / 'data/prepared_5K/events.parquet'))
    parser.add_argument('--lote', type=int, default=200)
    parser.add_argument('--tasa', type=float, default=0, help='Eventos por segundo; 0 = sin límite')
    parser.add_argument('--limite', type=int, default=0, help='Máximo de eventos del archivo; 0 = todos')
    parser.add_argument('--reenvios', type=float, default=0.0, help='Probabilidad de reenviar un evento')
    parser.add_argument('--invalidos', type=float, default=0.0, help='Probabilidad de inyectar un inválido')
    parser.add_argument('--semilla', type=int, default=2026)
    args = parser.parse_args()
    rng = random.Random(args.semilla)
    estados, latencias, total = Counter(), [], 0
    inicio = time.perf_counter()
    with httpx.Client(base_url=args.url, timeout=60) as cliente:
        for lote in lotes(args.eventos, args.lote, args.limite, args.reenvios, args.invalidos, rng):
            t0 = time.perf_counter()
            respuesta = cliente.post('/eventos/lote', json=lote)
            respuesta.raise_for_status()
            latencias.append(time.perf_counter() - t0)
            estados.update(respuesta.json()['resumen'])
            total += len(lote)
            if args.tasa:
                espera = inicio + total / args.tasa - time.perf_counter()
                if espera > 0:
                    time.sleep(espera)
            print(f'\r{total} enviados  {dict(estados)}', end='', flush=True)
    duracion = time.perf_counter() - inicio
    latencias.sort()
    print(f'\nTotal: {total} eventos en {duracion:.2f} s ({total / duracion:.0f} ev/s)')
    if latencias:
        print(f'Latencia por lote: p50={latencias[len(latencias) // 2] * 1000:.1f} ms  '
              f'p95={latencias[int(len(latencias) * 0.95)] * 1000:.1f} ms  max={latencias[-1] * 1000:.1f} ms')
    print('Estados:', dict(estados))


if __name__ == '__main__':
    main()
