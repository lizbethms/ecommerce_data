"""Panel de ventas, actividad y alertas.

Los montos se acumulan con Decimal. Las ventas se indexan en un B+Tree por
tiempo (epoch) para resolver consultas por rango de fechas. La actividad se
agrega por minuto del tiempo del evento.
"""
from collections import Counter
from decimal import Decimal

from src.structures.bplus_tree import BPlusTree
from src.structures.hash_table import HashTable
from src.structures.topk import top_k

from .base import Servicio, epoch


class ServicioPanel(Servicio):
    nombre = 'panel'

    def __init__(self, config, catalogo, fraude, priorizacion):
        super().__init__(config)
        self.catalogo, self.fraude, self.priorizacion = catalogo, fraude, priorizacion
        self.ingesta = None  # lo asigna el sistema
        self.por_tipo = Counter()
        self.por_origen = Counter()
        self.por_minuto = Counter()
        self.bruto = Decimal('0.00')
        self.devuelto = Decimal('0.00')
        self.unidades = self.unidades_devueltas = 0
        self.ordenes = HashTable(1024)
        self.ventas_producto = HashTable(1024)
        self.ventas_tiempo = BPlusTree(config.orden_bplus)
        self.primer_evento = self.ultimo_evento = None

    def procesar(self, evento, contexto):
        tipo, momento = evento['event_type'], evento['event_time']
        self.por_tipo[tipo] += 1
        self.por_origen[evento['event_origin'] or 'externo'] += 1
        self.por_minuto[momento[:16]] += 1
        self.primer_evento = min(self.primer_evento or momento, momento)
        self.ultimo_evento = max(self.ultimo_evento or momento, momento)
        if tipo in {'purchase', 'return'} and evento['price'] is not None:
            monto = Decimal(evento['price']) * evento['quantity']
            if tipo == 'purchase':
                self.bruto += monto
                self.unidades += evento['quantity']
                self.ordenes[evento['order_id']] = True
                self.ventas_producto[evento['product_id']] = self.ventas_producto.get(evento['product_id'], Decimal(0)) + monto
                self.ventas_tiempo.insert(epoch(momento), (evento['product_id'], monto))
            else:
                self.devuelto += monto
                self.unidades_devueltas += evento['quantity']
        return None

    def ventas_rango(self, desde, hasta):
        total, unidades = Decimal('0.00'), 0
        for _, (_, monto) in self.ventas_tiempo.range(epoch(desde), epoch(hasta)):
            total += monto
            unidades += 1
        return {'desde': desde, 'hasta': hasta, 'monto': str(total), 'lineas_de_compra': unidades}

    def resumen(self, minutos=30, k=5):
        ultimos = sorted(self.por_minuto.items())[-minutos:]
        mejores = top_k(self.ventas_producto.items(), k, key=lambda item: item[1])
        ordenes = len(self.ordenes)
        return {
            'ventas': {'monto_bruto': str(self.bruto), 'monto_devuelto': str(self.devuelto),
                       'monto_neto': str(self.bruto - self.devuelto), 'unidades': self.unidades,
                       'unidades_devueltas': self.unidades_devueltas, 'ordenes': ordenes,
                       'ticket_promedio': str((self.bruto / ordenes).quantize(Decimal('0.01'))) if ordenes else None},
            'top_productos_por_ventas': [dict(self.catalogo.obtener(p) or {'product_id': p}, ventas=str(m))
                                         for p, m in mejores],
            'top_productos_por_popularidad': [{'product_id': p['product_id'], 'nombre': p['nombre'],
                                               'popularidad': round(p['popularidad'], 2)}
                                              for p in self.catalogo.populares(k)],
            'actividad': {'por_tipo': dict(self.por_tipo), 'por_origen': dict(self.por_origen),
                          'por_minuto': [{'minuto': m, 'eventos': n} for m, n in ultimos],
                          'primer_evento': self.primer_evento, 'ultimo_evento': self.ultimo_evento},
            'alertas': {'total': len(self.fraude.alertas),
                        'bloqueos': sum(1 for a in self.fraude.alertas if a['decision'] == 'bloquear'),
                        'recientes': self.fraude.lista_alertas(limite=k)},
            'cola_ordenes': {**self.priorizacion.estadisticas(), 'siguientes': self.priorizacion.cola(k)},
            'ingesta': self.ingesta.estadisticas() if self.ingesta else None,
        }
