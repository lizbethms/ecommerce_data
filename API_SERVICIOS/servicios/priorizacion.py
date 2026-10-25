"""Priorización de órdenes con un heap mínimo.

Clave (clase, plazo, llegada):
- clase 0: alertas de pago o fraude, siempre primero;
- clase 1: órdenes por plazo más próximo (EDF). Express vence a las +4 h,
  estándar a las +48 h y programada en su ``scheduled_at``. Ordenar por plazo
  y no por clase fija evita la inanición: una estándar antigua termina
  adelantando a una express recién llegada.
La secuencia de llegada del heap desempata de forma estable. Cada orden entra
una sola vez: las compras siguientes de la misma orden solo agregan productos.
"""
from collections import deque
from datetime import datetime, timedelta, timezone

from src.structures.hash_table import HashTable
from src.structures.heap import MinHeap

from .base import Servicio, epoch


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace('+00:00', 'Z')


class ServicioPriorizacion(Servicio):
    nombre = 'priorizacion'
    tipos = frozenset({'purchase', 'payment_attempt'})

    def __init__(self, config, fraude):
        super().__init__(config)
        self.fraude = fraude
        self.heap = MinHeap()
        self.ordenes = HashTable(1024)  # order_id -> elemento (en cola o atendido)
        self.atendidos = deque(maxlen=200)
        self.encoladas = {'alerta': 0, 'orden': 0}
        self.pico = 0

    def plazo(self, evento):
        llegada = epoch(evento['event_time'])
        tipo = evento['delivery_type'] or 'standard'
        if tipo == 'scheduled' and evento['scheduled_at']:
            return epoch(evento['scheduled_at'])
        horas = self.config.plazo_express_h if tipo == 'express' else self.config.plazo_standard_h
        return llegada + timedelta(hours=horas).total_seconds()

    def _encolar(self, clase, plazo, elemento):
        self.heap.push((clase, plazo), elemento)
        self.encoladas[elemento['tipo']] += 1
        self.pico = max(self.pico, len(self.heap))

    def procesar(self, evento, contexto):
        if evento['event_type'] == 'payment_attempt':
            alerta = (contexto.get('fraude') or {}).get('alerta')
            if alerta and alerta['nueva']:
                ts = epoch(evento['event_time'])
                self._encolar(0, ts, dict(tipo='alerta', alerta_id=alerta['alerta_id'], order_id=evento['order_id'],
                                          user_id=evento['user_id'], llegada=evento['event_time'], estado='en_cola'))
                return {'encolado': 'alerta', 'alerta_id': alerta['alerta_id']}
            return None
        orden = self.ordenes.get(evento['order_id'])
        if orden is not None:
            if evento['product_id'] not in orden['productos']:
                orden['productos'].append(evento['product_id'])
            return {'encolado': None, 'order_id': evento['order_id'], 'productos_en_orden': len(orden['productos'])}
        plazo = self.plazo(evento)
        orden = dict(tipo='orden', order_id=evento['order_id'], user_id=evento['user_id'],
                     delivery_type=evento['delivery_type'] or 'standard', llegada=evento['event_time'],
                     plazo=_iso(plazo), productos=[evento['product_id']], estado='en_cola')
        self.ordenes[evento['order_id']] = orden
        self._encolar(1, plazo, orden)
        return {'encolado': 'orden', 'order_id': evento['order_id'], 'plazo': orden['plazo']}

    def _vista(self, clave, elemento):
        vista = dict(elemento, clase='alerta' if clave[0] == 0 else 'orden')
        if elemento['tipo'] == 'alerta':
            alerta = self.fraude.alerta(elemento['alerta_id'])
            if alerta:
                vista.update(decision=alerta['decision'], intentos=alerta['intentos'])
        return vista

    def cola(self, n=20):
        return [self._vista(clave, elemento) for clave, elemento in self.heap.smallest(n)]

    def atender(self, n=1):
        """Extrae los n más urgentes. Una orden bloqueada por fraude queda retenida."""
        atendidos = []
        for _ in range(min(n, len(self.heap))):
            clave, elemento = self.heap.pop()
            if elemento['tipo'] == 'orden':
                bloqueada = self.fraude.orden_bloqueada(elemento['order_id'])
                elemento['estado'] = 'retenida_por_fraude' if bloqueada else 'despachada'
            else:
                elemento['estado'] = 'revisada'
            vista = self._vista(clave, elemento)
            self.atendidos.append(vista)
            atendidos.append(vista)
        return atendidos

    def estado_orden(self, order_id):
        orden = self.ordenes.get(order_id)
        return dict(orden, bloqueada_por_fraude=self.fraude.orden_bloqueada(order_id)) if orden else None

    def estadisticas(self):
        return dict(super().estadisticas(), en_cola=len(self.heap), pico_cola=self.pico,
                    encoladas=dict(self.encoladas), atendidos_recientes=len(self.atendidos))
