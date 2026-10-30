"""Verifica el flujo del README sobre una API local recién iniciada y sin precarga.

Ejecutar: .venv/bin/python scripts/verificar_api_funcional.py
Reproduce el cliente oficial y compara ventas, stock y co-compra con el Parquet.
Guarda evidencia en results/api_funcional.json (incluido si una comprobación falla).
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from itertools import combinations
import json
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx

from src.data.parquet_io import iter_events, iter_rows
from API_SERVICIOS.cliente_trafico import lotes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--datos', type=Path, default=ROOT / 'data/prepared_5K')
    parser.add_argument('--salida', type=Path, default=ROOT / 'results/api_funcional.json')
    args = parser.parse_args()
    evidence = {'fecha_utc': datetime.now(timezone.utc).isoformat(), 'comprobaciones': []}

    def check(name, condition, detail=None):
        evidence['comprobaciones'].append({'caso': name, 'ok': bool(condition), 'detalle': detail})
        if not condition:
            raise AssertionError(f'{name}: {detail}')

    try:
        with httpx.Client(base_url=args.url, timeout=120) as api:
            def request(method, path, **kwargs):
                response = api.request(method, path, **kwargs)
                response.raise_for_status()
                return response.json()

            salud = request('GET', '/salud')
            evidence['salud_inicial'] = salud
            check('API con catálogo y sin eventos precargados',
                  salud['estado'] == 'ok' and salud['productos'] > 0 and salud['eventos_aceptados'] == 0
                  and salud['carga']['eventos_precargados'] == 0, salud)
            unique = {}
            source_count = 0
            for event in iter_events(args.datos / 'events.parquet'):
                source_count += 1
                unique.setdefault(event['event_id'], event)
            types = Counter(e['event_type'] for e in unique.values())
            purchases = [e for e in unique.values() if e['event_type'] == 'purchase']
            returns = [e for e in unique.values() if e['event_type'] == 'return']
            amount = lambda rows: sum((Decimal(e['price']) * e['quantity'] for e in rows), Decimal('0.00'))
            orders = defaultdict(set)
            sold, returned = Counter(), Counter()
            for e in purchases:
                orders[e['order_id']].add(e['product_id'])
                sold[e['product_id']] += e['quantity']
            for e in returns:
                returned[e['product_id']] += e['quantity']
            pairs = Counter(pair for products in orders.values() for pair in combinations(sorted(products), 2))
            command = [sys.executable, '-m', 'API_SERVICIOS.cliente_trafico', '--url', args.url,
                       '--eventos', str(args.datos / 'events.parquet'), '--lote', '250',
                       '--reenvios', '0.02', '--invalidos', '0.01', '--semilla', '2026']
            run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            evidence['cliente'] = {'comando': command, 'codigo_salida': run.returncode,
                                   'salida': run.stdout, 'errores': run.stderr}
            check('Cliente oficial completa todos los lotes HTTP', run.returncode == 0, run.stderr)
            stats = request('GET', '/admin/estadisticas')
            panel = request('GET', '/panel')
            evidence.update(estadisticas=stats, panel=panel,
                            fuente={'filas': source_count, 'ids_unicos': len(unique), 'tipos': dict(types)})
            check('Aceptados coinciden con identidades únicas', stats['ingesta']['aceptados'] == len(unique))
            sent = [e for batch in lotes(args.datos / 'events.parquet', 250, 0, 0.02, 0.01,
                                        random.Random(2026)) for e in batch]
            invalid_count = sum(e['event_id'].startswith('invalido:') for e in sent)
            check('Conteos exactos de reenvíos e inválidos', stats['ingesta']['duplicados'] ==
                  len(sent) - invalid_count - len(unique) and stats['ingesta']['rechazados'] == invalid_count,
                  {'enviados': len(sent), 'invalidos': invalid_count, **stats['ingesta']})
            check('Panel recibe todos los tipos de evento', panel['actividad']['por_tipo'] == dict(types))
            sales = panel['ventas']
            check('Ventas, devoluciones, unidades y órdenes exactas',
                  Decimal(sales['monto_bruto']) == amount(purchases)
                  and Decimal(sales['monto_devuelto']) == amount(returns)
                  and Decimal(sales['monto_neto']) == amount(purchases) - amount(returns)
                  and sales['unidades'] == sum(sold.values())
                  and sales['unidades_devueltas'] == sum(returned.values())
                  and sales['ordenes'] == len(orders), sales)
            inventory = {r['product_id']: r['supplied'] + 10 for r in iter_rows(args.datos / 'inventory.parquet')}
            for pid in sold.keys() | returned.keys():
                product = request('GET', f'/productos/{pid}')
                check(f'Stock y contadores producto {pid}',
                      product['stock'] == inventory[pid] - sold[pid] + returned[pid]
                      and product['vendidos'] == sold[pid] and product['devueltos'] == returned[pid])
            actual_pairs = request('GET', '/cocompra/pares', params={'k': 200})
            check('Co-compra por órdenes distintas', bool(actual_pairs) and all(
                pairs[tuple(sorted((p['producto_a'], p['producto_b'])))] == p['ordenes_compartidas']
                for p in actual_pairs))
            first, last = min(e['event_time'] for e in unique.values()), max(e['event_time'] for e in unique.values())
            range_sales = request('GET', '/panel/ventas', params={'desde': first, 'hasta': last})
            check('Ventas por rango temporal', Decimal(range_sales['monto']) == amount(purchases)
                  and range_sales['lineas_de_compra'] == len(purchases), range_sales)
            event = purchases[0]
            before = request('GET', '/productos/' + event['product_id'])
            repeat = request('POST', '/eventos', json=event)
            conflict = request('POST', '/eventos', json=dict(event, price='999999.99'))
            after = request('GET', '/productos/' + event['product_id'])
            check('Reenvío y conflicto sin efectos secundarios', repeat['estado'] == 'duplicado'
                  and conflict['estado'] == 'rechazado'
                  and all(before[k] == after[k] for k in ('stock', 'vendidos', 'devueltos', 'popularidad'))
                  and request('GET', '/panel')['ventas'] == sales, {'reenvio': repeat, 'conflicto': conflict})
            evidence['reconstruccion'] = request('POST', '/admin/reconstruir')
            pid = event['product_id']
            probes = [('/categorias', {}), ('/productos', {'precio_min': 1, 'precio_max': 2000}),
                      ('/productos', {'categoria': 'electronics'}),
                      ('/buscar/autocompletar', {'prefijo': 'sa'}),
                      ('/buscar', {'q': 'samsung', 'orden': 'relevancia'}),
                      ('/buscar', {'q': 'samsung', 'orden': 'popularidad'}),
                      ('/cocompra/influyentes', {}), ('/cocompra/comunidades', {}),
                      (f'/productos/{pid}/complementarios', {}),
                      (f'/cocompra/productos/{pid}/cross-selling', {}),
                      (f'/usuarios/{event["user_id"]}/recomendaciones', {}),
                      ('/fraude/alertas', {}), ('/fraude/estadisticas', {})]
            probes.extend((f'/productos/{pid}/similares', {'metodo': m}) for m in ('knn', 'hnsw', 'minhash'))
            evidence['consultas'] = []
            for path, params in probes:
                body = request('GET', path, params=params)
                evidence['consultas'].append({'ruta': path, 'parametros': params, 'respuesta': body})
                check(f'Consulta HTTP {path} {params}', body is not None)
            evidence['atencion'] = []
            while True:
                queue = request('GET', '/ordenes/cola', params={'n': 500})
                if not queue['en_cola']:
                    break
                served = request('POST', '/ordenes/atender', params={'n': 500})
                check('Atención respeta el orden de la cola', served['atendidos'] == [
                    dict(item, estado=('revisada' if item['clase'] == 'alerta' else
                         'retenida_por_fraude' if request('GET', '/ordenes/' + item['order_id'])['bloqueada_por_fraude']
                         else 'despachada')) for item in queue['siguientes']])
                evidence['atencion'].extend(served['atendidos'])
            retained = sum(x['estado'] == 'retenida_por_fraude' for x in evidence['atencion'])
            check('Órdenes bloqueadas quedan retenidas', retained > 0, {'retenidas': retained})
            evidence['resultado'] = 'APROBADO'
    except Exception as error:
        evidence.update(resultado='FALLIDO', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
        print(f'{evidence["resultado"]}: {len(evidence["comprobaciones"])} comprobaciones. {args.salida}')


if __name__ == '__main__':
    main()
