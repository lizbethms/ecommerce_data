"""Una orden atraviesa las diez etapas del pipeline y produce una salida observable en cada una.

La orden es un intento de pago fallido más dos compras. El pago pasa por fraude (etapa 6) y la
compra por el grafo de co-compra (etapa 8); juntas recorren las etapas 0–9. Sin --url, la API
corre en este proceso: se carga el catálogo, se envía events.parquet por /eventos/lote y luego la
orden. Con --url, se usa una API ya iniciada (con tráfico previo).

Ejemplo:
  python scripts/recorrido_evento.py --datos data/prepared/perfil_1K
"""
import argparse
from contextlib import nullcontext
from datetime import timedelta, timezone
from decimal import Decimal
import json
import random
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
import pyarrow.compute as pc
import pyarrow.parquet as pq

from API_SERVICIOS.cliente_trafico import lotes
from src.data.parquet_io import iter_rows

USUARIO, ORDEN = 'demo:recorrido:usuario', 'demo:recorrido:orden'


def productos_demo(datos):
    """Dos productos del catálogo con categoría y precio: el primero es el que se sigue en cada etapa."""
    elegidos = [r for r in iter_rows(datos / 'catalog.parquet')
                if r['category_code'] and r['brand'] and r['last_observed_price']][:2]
    if len(elegidos) < 2:
        raise SystemExit('El catálogo necesita al menos dos productos con categoría, marca y precio')
    return elegidos


def evento(eid, tipo, momento, producto, **extra):
    return dict(event_id=f'demo:recorrido:{eid}', event_type=tipo, event_time=momento, user_id=USUARIO,
                user_session='demo:recorrido:sesion', product_id=producto['product_id'],
                category_id=producto['category_id'], category_code=producto['category_code'],
                brand=producto['brand'], price=str(Decimal(str(producto['last_observed_price']))), **extra)


def posicion_en_cola(cola):
    siguientes = cola['siguientes']
    posiciones = [(i + 1, x['clase']) for i, x in enumerate(siguientes) if x.get('order_id') == ORDEN]
    alertas = sum(1 for x in siguientes if x['clase'] == 'alerta')
    return (f'la orden ocupa las posiciones {posiciones} de {cola["en_cola"]}; las {alertas} alertas (clase 0) '
            'se atienden antes que cualquier orden (clase 1, por plazo EDF)')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--datos', type=Path, default=ROOT / 'data/prepared/perfil_1K')
    parser.add_argument('--url', help='API ya iniciada; si se omite, se levanta una en este proceso')
    parser.add_argument('--salida', type=Path, help='JSON con las respuestas de cada etapa')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # Git Bash y consolas cp1252 de Windows
    eventos_archivo = args.datos / 'events.parquet'
    ultimo = pc.max(pq.read_table(eventos_archivo, columns=['event_time']).column(0)).as_py()
    t = lambda minutos: (ultimo.astimezone(timezone.utc) + timedelta(minutes=minutos)).strftime('%Y-%m-%dT%H:%M:%SZ')
    a, b = productos_demo(args.datos)

    if args.url:
        contexto = httpx.Client(base_url=args.url, timeout=120)
    else:
        from fastapi.testclient import TestClient
        from API_SERVICIOS.config import Config
        from API_SERVICIOS.main import create_app
        contexto = TestClient(create_app(Config(dir_datos=args.datos, precargar=False)))
    salida = {}
    with contexto as api:
        def q(metodo, ruta, **kwargs):
            respuesta = api.request(metodo, ruta, **kwargs)
            respuesta.raise_for_status()
            return respuesta.json()

        if not args.url:
            for lote in lotes(str(eventos_archivo), 500, 0, 0, 0, random.Random(2026)):
                q('POST', '/eventos/lote', json=lote)
        orden = [evento('pago', 'payment_attempt', t(1), a, order_id=ORDEN, payment_status='failed',
                        payment_attempt_id='demo:recorrido:intento', payment_method_id='demo:recorrido:tarjeta',
                        device_id='demo:recorrido:dispositivo'),
                 evento('compra_a', 'purchase', t(2), a, order_id=ORDEN, quantity=1, delivery_type='express'),
                 evento('compra_b', 'purchase', t(2), b, order_id=ORDEN, quantity=1, delivery_type='express')]
        ingreso = q('POST', '/eventos/lote', json=orden)
        reenvio = q('POST', '/eventos/lote', json=orden[1:2])
        q('POST', '/admin/reconstruir')  # KD-Tree, HNSW y LSH incorporan la orden sin esperar al intervalo
        pid, prefijo = a['product_id'], a['category_code'].split('.')[-1][:3]
        consultas = {
            'fifo': q('GET', '/admin/estadisticas')['fifo'],
            'cola': q('GET', '/ordenes/cola', params={'n': 500}),
            'producto_1': q('GET', f'/productos/{pid}'),
            'producto_2': q('GET', f'/productos/{pid}'),
            'ventas': q('GET', '/panel/ventas', params={'desde': t(0), 'hasta': t(3)}),
            'knn': q('GET', f'/productos/{pid}/similares', params={'metodo': 'knn', 'k': 3}),
            'alertas': [x for x in q('GET', '/fraude/alertas') if x.get('order_id') == ORDEN],
            'hnsw': q('GET', f'/productos/{pid}/similares', params={'metodo': 'hnsw', 'k': 3}),
            'cross_selling': q('GET', f'/cocompra/productos/{pid}/cross-selling', params={'k': 3}),
            'autocompletar': q('GET', '/buscar/autocompletar', params={'prefijo': prefijo, 'k': 3}),
            'panel': q('GET', '/panel', params={'k': 3}),
        }
    recorridos = {r['event_id'].split(':')[-1]: r['recorrido'] for r in ingreso['resultados']}
    etapas = sorted(set().union(*(r['etapas'] for r in recorridos.values())))
    c = consultas
    filas = [
        (0, 'FIFO acotada', f'{c["fifo"]["eventos"]} eventos pasaron por la cola; pico {c["fifo"]["pico"]} de '
                            f'{c["fifo"]["capacidad"]}; espera de la orden '
                            f'{max(r["espera_fifo_ms"] for r in recorridos.values()):.2f} ms'),
        (1, 'Merge sort + tabla hash', f'orden aceptada ({ingreso["resumen"]}); reenvío -> {reenvio["resumen"]}'),
        (2, 'MinHeap EDF', posicion_en_cola(c['cola'])),
        (3, 'Tabla hash + LRU', f'producto {pid}: 1.ª consulta {c["producto_1"]["cache"]}, '
                                f'2.ª {c["producto_2"]["cache"]}; vendidos={c["producto_2"].get("vendidos")}'),
        (4, 'B+Tree por tiempo', f'ventas del rango de la orden: {c["ventas"]["monto"]} '
                                 f'({c["ventas"]["lineas_de_compra"]} líneas)'),
        (5, 'KD-Tree (KNN exacto)', 'similares exactos: ' + ', '.join(x['product_id'] for x in c['knn']['resultados'])),
        (6, 'Bloom + CMS', 'alerta: ' + ', '.join(f'{x["alerta_id"]} ({x["decision"]})' for x in c['alertas'])),
        (7, 'HNSW', f'similares aproximados con recall {c["hnsw"]["recall_vs_exacto"]} frente al exacto'),
        (8, 'Grafo de co-compra', 'cross-selling: ' + ', '.join(
            f'{x["product_id"]} ({x.get("motivo")})' for x in c['cross_selling']['sugerencias'])),
        (9, 'Trie + Top-K', f'autocompletar "{prefijo}": ' + ', '.join(x['texto'] for x in c['autocompletar'][:3])
            + '; más vendidos: ' + ', '.join(str(x.get('product_id')) for x in c['panel'].get('top_productos_por_ventas', [])[:3])),
    ]
    print(f'Orden {ORDEN}: etapas atravesadas en la ingesta {etapas}')
    for nombre, recorrido in recorridos.items():
        print(f'  {nombre}: etapas {recorrido["etapas"]} (servicios: {", ".join(recorrido["servicios"])})')
    print()
    for etapa, estructura, observado in filas:
        print(f'{etapa}  {estructura:<24} {observado}')
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(json.dumps(dict(etapas=etapas, recorridos=recorridos, ingreso=ingreso,
                                               reenvio=reenvio, consultas=consultas), ensure_ascii=False,
                                          indent=2, default=str) + '\n', encoding='utf-8')
    if etapas != list(range(10)):
        raise SystemExit(f'La orden no recorrió las diez etapas: {etapas}')


if __name__ == '__main__':
    main()
