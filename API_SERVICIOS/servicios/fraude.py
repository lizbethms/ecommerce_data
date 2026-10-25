"""Posible fraude: pertenencia probabilística, intensidad por ventana y verificación exacta.

1. Bloom Filter con las cuentas, dispositivos y medios señalados. Un positivo
   se verifica siempre contra la tabla exacta: un falso positivo no bloquea.
2. Count-Min Sketch por ventana: estima los intentos de pago por clave en los
   últimos ``ventana_fraude_seg``. Si la estimación supera el umbral, se
   confirma con el conteo exacto de la ventana antes de bloquear (el CMS
   puede sobreestimar).
3. Decisión: bloquear (señal verificada o clave ya bloqueada), revisar (pago
   fallido sin otra señal) o permitir. Bloquear y revisar generan una alerta
   que Priorización atiende primero.
"""
from collections import deque

from src.structures.bloom import BloomFilter
from src.structures.count_min import WindowedCMS
from src.structures.hash_table import HashTable

from .base import Servicio, epoch

TIPOS_CLAVE = (('account', 'user_id'), ('device', 'device_id'), ('payment_method', 'payment_method_id'))


class ServicioFraude(Servicio):
    nombre = 'fraude'
    tipos = frozenset({'payment_attempt'})

    def __init__(self, config):
        super().__init__(config)
        self.senalados = HashTable()  # registro exacto: 'tipo:valor' -> motivo
        self.bloom = BloomFilter(1024, config.bloom_fp)
        self.cms = WindowedCMS(config.ventana_fraude_seg, config.sub_ventanas, config.cms_ancho, config.cms_profundidad)
        self.exacto = HashTable()  # 'tipo:valor' -> deque de tiempos dentro de la ventana
        self.bloqueados = HashTable()  # clave -> motivo
        self.ordenes_bloqueadas = HashTable()
        self.alertas = []
        self._alerta_por_clave = HashTable()
        self.ultimo_tiempo = None
        self.metricas = dict(consultas_bloom=0, positivos_bloom=0, verificados=0, falsos_positivos_bloom=0,
                             cms_sobre_umbral=0, cms_sobreestimaciones=0, intensidad_confirmada=0,
                             decisiones={'permitir': 0, 'revisar': 0, 'bloquear': 0})

    # ---------- señalados ----------
    def cargar_senalados(self, filas):
        filas = list(filas)
        # Capacidad holgada (2n) para admitir señalamientos manuales sin superar la tasa objetivo.
        self.bloom = BloomFilter(max(64, 2 * len(filas)), self.config.bloom_fp)
        for fila in filas:
            self.senalar(fila['kind'], fila['value'], fila['reason'])

    def senalar(self, tipo, valor, motivo='manual'):
        clave = f'{tipo}:{valor}'
        self.senalados[clave] = motivo
        self.bloom.add(clave)
        return clave

    # ---------- ventana exacta (solo para verificar) ----------
    def _conteo_exacto(self, clave, ts, registrar):
        inicio = ts - self.config.ventana_fraude_seg
        tiempos = self.exacto.get(clave)
        if not registrar:  # una consulta no modifica el estado
            return sum(1 for t in tiempos or () if inicio < t <= ts)
        if tiempos is None:
            tiempos = self.exacto[clave] = deque()
        tiempos.append(ts)
        while tiempos and tiempos[0] <= inicio:
            tiempos.popleft()
        return sum(1 for t in tiempos if t <= ts)

    # ---------- evaluación ----------
    def evaluar(self, user_id=None, device_id=None, payment_method_id=None, ts=None, estado_pago=None,
                registrar=True):
        ts = ts if ts is not None else (self.ultimo_tiempo or 0.0)
        valores = {'user_id': user_id, 'device_id': device_id, 'payment_method_id': payment_method_id}
        senales, notas, intensidad = [], [], {}
        for tipo, campo in TIPOS_CLAVE:
            valor = valores[campo]
            if not valor:
                continue
            clave = f'{tipo}:{valor}'
            if registrar:
                self.cms.add(clave, ts)
            exacto = self._conteo_exacto(clave, ts, registrar)
            self.metricas['consultas_bloom'] += 1
            if clave in self.bloom:
                self.metricas['positivos_bloom'] += 1
                motivo = self.senalados.get(clave)
                if motivo is not None:
                    self.metricas['verificados'] += 1
                    senales.append({'tipo': f'{tipo}_senalado', 'clave': clave, 'motivo': motivo})
                else:
                    self.metricas['falsos_positivos_bloom'] += 1
                    notas.append(f'falso positivo del Bloom descartado por verificación exacta: {clave}')
            estimado = self.cms.estimate(clave, ts)
            intensidad[clave] = {'estimado_cms': estimado, 'exacto': exacto}
            if estimado >= self.config.umbral_intentos:
                self.metricas['cms_sobre_umbral'] += 1
                if exacto >= self.config.umbral_intentos:
                    self.metricas['intensidad_confirmada'] += 1
                    senales.append({'tipo': 'intensidad', 'clave': clave, 'estimado_cms': estimado, 'exacto': exacto,
                                    'ventana_seg': self.config.ventana_fraude_seg})
                else:
                    self.metricas['cms_sobreestimaciones'] += 1
                    notas.append(f'CMS sobre el umbral pero el conteo exacto no lo confirma: {clave}')
            if clave in self.bloqueados:
                senales.append({'tipo': 'bloqueo_previo', 'clave': clave, 'motivo': self.bloqueados[clave]})
        if senales:
            decision = 'bloquear'
        elif estado_pago == 'failed':
            decision = 'revisar'
        else:
            decision = 'permitir'
        return {'decision': decision, 'senales': senales, 'notas': notas, 'intensidad': intensidad}

    def procesar(self, evento, contexto):
        ts = epoch(evento['event_time'])
        self.ultimo_tiempo = max(ts, self.ultimo_tiempo or ts)
        resultado = self.evaluar(evento['user_id'], evento['device_id'], evento['payment_method_id'], ts,
                                 evento['payment_status'])
        decision = resultado['decision']
        self.metricas['decisiones'][decision] += 1
        if decision == 'bloquear':
            for senal in resultado['senales']:
                if senal['tipo'] != 'bloqueo_previo':
                    self.bloqueados[senal['clave']] = senal['tipo']
            self.ordenes_bloqueadas[evento['order_id']] = evento['event_id']
        if decision != 'permitir':
            resultado['alerta'] = self._alertar(evento, resultado)
        return resultado

    def _alertar(self, evento, resultado):
        """Una alerta por orden: los intentos siguientes la actualizan en vez de duplicarla."""
        clave = evento['order_id'] or evento['user_id']
        alerta = self._alerta_por_clave.get(clave)
        if alerta is None:
            alerta = dict(alerta_id=f'alerta:{len(self.alertas) + 1}', order_id=evento['order_id'],
                          user_id=evento['user_id'], primer_evento=evento['event_id'],
                          creada=evento['event_time'], intentos=0, nueva=True)
            self._alerta_por_clave[clave] = alerta
            self.alertas.append(alerta)
        else:
            alerta['nueva'] = False
        severidad = 'bloquear' if resultado['decision'] == 'bloquear' else 'revisar'
        if alerta.get('decision') != 'bloquear':
            alerta['decision'] = severidad  # una alerta solo puede escalar
        alerta.update(intentos=alerta['intentos'] + 1, ultimo_evento=evento['event_id'],
                      actualizada=evento['event_time'], senales=resultado['senales'])
        return {k: alerta[k] for k in ('alerta_id', 'decision', 'intentos', 'nueva')}

    # ---------- consultas ----------
    def lista_alertas(self, decision=None, limite=50):
        alertas = [a for a in reversed(self.alertas) if decision is None or a['decision'] == decision]
        return [{k: v for k, v in a.items() if k != 'nueva'} for a in alertas[:limite]]

    def alerta(self, alerta_id):
        indice = int(alerta_id.split(':')[1]) - 1
        return self.alertas[indice] if 0 <= indice < len(self.alertas) else None

    def orden_bloqueada(self, order_id):
        return order_id in self.ordenes_bloqueadas

    def estadisticas(self):
        return dict(super().estadisticas(), senalados=len(self.senalados), bloom=self.bloom.stats(),
                    cms=self.cms.stats(), claves_bloqueadas=len(self.bloqueados),
                    ordenes_bloqueadas=len(self.ordenes_bloqueadas), alertas=len(self.alertas), **self.metricas)
