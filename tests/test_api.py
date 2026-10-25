"""Comportamiento observable de la API con tráfico controlado (sin depender de data/)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from API_SERVICIOS.config import Config
from API_SERVICIOS.main import create_app

PRODUCTOS = {
    'A': ('100', 'electronics.smartphone', 'samsung', '200.00'),
    'B': ('100', 'electronics.audio.headphone', 'sony', '50.00'),
    'C': ('200', 'appliances.kitchen.kettle', 'bosch', '30.00'),
}


def evento(eid, tipo, minuto, producto=None, **extra):
    base = dict(event_id=eid, event_type=tipo, event_time=f'2019-10-01T10:{minuto:02d}:00Z',
                user_id=extra.pop('user_id', 'u1'), user_session='s1')
    if producto:
        cid, code, brand, price = PRODUCTOS[producto]
        base.update(product_id=producto, category_id=cid, category_code=code, brand=brand, price=price)
    base.update(extra)
    return base


def compra(eid, minuto, producto, orden, entrega='standard', **extra):
    return evento(eid, 'purchase', minuto, producto, order_id=orden, quantity=1, delivery_type=entrega, **extra)


def pago(eid, minuto, orden, estado='succeeded', user='u1', metodo='m1', dispositivo='d1'):
    return evento(eid, 'payment_attempt', minuto, 'A', order_id=orden, user_id=user, payment_status=estado,
                  payment_attempt_id=f'pa:{eid}', payment_method_id=metodo, device_id=dispositivo)


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.contexto = TestClient(create_app(Config(dir_datos=None, reconstruir_cada_seg=0)))
        self.api = self.contexto.__enter__()

    def tearDown(self):
        self.contexto.__exit__(None, None, None)

    def lote(self, eventos):
        respuesta = self.api.post('/eventos/lote', json=eventos)
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        return respuesta.json()

    def test_validacion_y_rechazo_observable(self):
        r = self.lote([evento('x1', 'teleport', 1, 'A'), evento('x2', 'view', 1),
                       evento('x3', 'view', 1, 'A', price='-1'), evento('x4', 'view', 1, 'A', event_time='mañana')])
        self.assertEqual(r['resumen'], {'rechazado': 4})
        self.assertTrue(all(x['motivo'] for x in r['resultados']))

    def test_duplicados_e_identidad(self):
        original = evento('e1', 'view', 1, 'A')
        r = self.lote([original, dict(original), evento('e2', 'cart', 2, 'A')])
        self.assertEqual(r['resumen'], {'aceptado': 2, 'duplicado': 1})
        self.assertEqual(self.api.post('/eventos', json=original).json()['estado'], 'duplicado')
        conflicto = self.api.post('/eventos', json=dict(original, product_id='B')).json()
        self.assertEqual(conflicto['estado'], 'rechazado')
        self.assertEqual(self.api.get('/productos/A').json()['vistas'], 1)

    def test_prioridad_alerta_express_estandar_programada(self):
        self.api.post('/fraude/senalados', params={'tipo': 'payment_method', 'valor': 'robado'})
        self.lote([
            compra('p1', 1, 'C', 'o-prog', 'scheduled', scheduled_at='2019-10-04T10:00:00Z'),  # vence después de +48 h
            compra('p2', 2, 'B', 'o-std', 'standard'),
            compra('p3', 3, 'A', 'o-exp', 'express'),
            pago('f1', 4, 'o-fraude', 'failed', user='u9', metodo='robado'),
        ])
        atendidos = self.api.post('/ordenes/atender', params={'n': 4}).json()['atendidos']
        self.assertEqual([a['clase'] for a in atendidos], ['alerta', 'orden', 'orden', 'orden'])
        self.assertEqual([a['order_id'] for a in atendidos], ['o-fraude', 'o-exp', 'o-std', 'o-prog'])
        self.assertEqual(atendidos[0]['decision'], 'bloquear')

    def test_fraude_verifica_antes_de_bloquear(self):
        r = self.lote([pago(f'q{i}', 1, 'o-r', 'failed', user='u7', metodo=f'm{i}', dispositivo=f'd{i}')
                       for i in range(6)])
        decisiones = [x['resultados']['fraude']['decision'] for x in r['resultados']]
        self.assertEqual(decisiones[:4], ['revisar'] * 4)  # fallidos, aún bajo el umbral
        self.assertEqual(decisiones[4:], ['bloquear'] * 2)
        senal = r['resultados'][4]['resultados']['fraude']['senales'][0]
        self.assertEqual((senal['tipo'], senal['exacto']), ('intensidad', 5))
        # Intentos espaciados más que la ventana nunca alcanzan el umbral.
        espaciados = self.lote([pago(f'w{i}', i * 11, f'o-w{i}', user='u8') for i in range(5)])
        self.assertTrue(all(x['resultados']['fraude']['decision'] == 'permitir' for x in espaciados['resultados']))
        self.assertEqual(self.api.post('/fraude/verificar', json={'user_id': 'nadie'}).json()['decision'], 'permitir')
        # La compra de la orden bloqueada queda retenida al atenderla.
        self.lote([compra('c-r', 2, 'A', 'o-r', user_id='u7')])
        estados = {a.get('order_id'): a['estado'] for a in self.api.post('/ordenes/atender', params={'n': 10}).json()['atendidos']}
        self.assertEqual(estados['o-r'], 'retenida_por_fraude')

    def test_cocompra_idempotente(self):
        primera = [compra('a1', 1, 'A', 'o1'), compra('b1', 1, 'B', 'o1')]
        self.lote(primera)
        self.lote(primera + [compra('a1-otra-unidad', 2, 'A', 'o1')])  # reenvío + mismo producto en la orden
        self.assertEqual(self.api.get('/cocompra/pares').json()[0]['ordenes_compartidas'], 1)
        self.lote([compra('a2', 3, 'A', 'o2'), compra('b2', 3, 'B', 'o2'), compra('c2', 3, 'C', 'o2')])
        pares = {(p['producto_a'], p['producto_b']): p['ordenes_compartidas'] for p in self.api.get('/cocompra/pares').json()}
        self.assertEqual(pares.get(('A', 'B'), pares.get(('B', 'A'))), 2)
        sugerencias = self.api.get('/cocompra/productos/A/cross-selling').json()['sugerencias']
        self.assertEqual(sugerencias[0]['product_id'], 'B')
        self.assertEqual(len(self.api.get('/cocompra/influyentes', params={'k': 3}).json()), 3)
        self.assertIn('modularidad', self.api.get('/cocompra/comunidades', params={'min_tamano': 1}).json())

    def test_catalogo_busqueda_recomendacion_y_panel(self):
        self.lote([evento('v1', 'view', 1, 'A'), evento('v2', 'view', 1, 'B'), evento('v3', 'view', 1, 'C'),
                   evento('s1', 'search', 2, query='samsung'),
                   compra('k1', 3, 'A', 'o1'), compra('k2', 3, 'B', 'o1'),
                   evento('v4', 'view', 4, 'C', user_id='u2'), evento('v5', 'view', 4, 'A', user_id='u2')])
        self.assertEqual(self.api.get('/productos/A').json()['cache'], 'miss')
        self.assertEqual(self.api.get('/productos/A').json()['cache'], 'hit')
        self.assertEqual(self.api.get('/productos/zzz').status_code, 404)
        rango = self.api.get('/productos', params={'precio_min': 40, 'precio_max': 250}).json()['resultados']
        self.assertEqual([p['product_id'] for p in rango], ['B', 'A'])
        self.assertEqual([p['product_id'] for p in self.api.get('/productos', params={'categoria': 'electronics'}).json()['resultados']],
                         ['B', 'A'])
        sugerencias = [s['texto'] for s in self.api.get('/buscar/autocompletar', params={'prefijo': 'sa'}).json()]
        self.assertIn('samsung', sugerencias)
        self.assertEqual(self.api.get('/buscar', params={'q': 'samsung smartphone'}).json()['resultados'][0]['product_id'], 'A')
        for metodo in ('knn', 'hnsw', 'minhash'):
            r = self.api.get('/productos/A/similares', params={'metodo': metodo, 'k': 2})
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.api.get('/productos/A/similares', params={'metodo': 'knn', 'k': 2}).json()['resultados'][0]['product_id'], 'B')
        recomendados = self.api.get('/usuarios/u2/recomendaciones').json()
        self.assertEqual(recomendados['estrategia'], 'hibrida')
        self.assertIn('B', [p['product_id'] for p in recomendados['resultados']])
        panel = self.api.get('/panel').json()
        self.assertEqual(panel['ventas']['monto_bruto'], '250.00')
        self.assertEqual(panel['ventas']['ordenes'], 1)
        ventas = self.api.get('/panel/ventas', params={'desde': '2019-10-01T10:00:00Z', 'hasta': '2019-10-01T10:03:00Z'}).json()
        self.assertEqual(ventas['monto'], '250.00')


if __name__ == '__main__':
    unittest.main()
