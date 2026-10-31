"""Etapa 0 en la ruta HTTP: los eventos entran a una BoundedFIFO y un consumidor los agrupa en lotes.

Cada petición deja sus eventos en la cola; si está llena, `put` espera (contrapresión). Un único
consumidor vacía lo disponible en un lote (etapa 1: orden y deduplicación en ServicioIngesta) y
devuelve a cada evento su resultado mediante un Future, con el recorrido de etapas que atravesó.
"""
import asyncio
import time

from src.structures.fifo import BoundedFIFO

# Etapas del pipeline que toca cada servicio al procesar un evento (ver README, mapa de etapas).
ETAPAS_POR_SERVICIO = {
    'catalogo': (3, 4),        # tabla hash + LRU; B+Tree por precio y categoría
    'fraude': (6,),            # Bloom + CMS por ventanas
    'priorizacion': (2,),      # MinHeap EDF
    'cocompra': (8,),          # grafo ponderado (PageRank y comunidades al consultar)
    'recomendacion': (3, 5, 7),  # matriz dispersa; KD-Tree, HNSW y LSH en la próxima reconstrucción
    'busqueda': (9,),          # Trie ponderado
    'panel': (4, 9),           # B+Tree de ventas por tiempo; Top-K
}
_FIN = object()


class CanalIngesta:
    def __init__(self, sistema, capacidad, lote_maximo):
        self.sistema = sistema
        self.fifo = BoundedFIFO(capacidad)
        self.lote_maximo = lote_maximo
        self.lotes = self.eventos = 0
        self.tarea = None

    async def iniciar(self):
        self.tarea = asyncio.create_task(self._consumir())

    async def detener(self):
        if self.tarea and not self.tarea.done():
            await self.fifo.put(_FIN)
            await self.tarea

    async def enviar(self, eventos):
        """Encola los eventos en orden y espera sus resultados (mismo orden que la petición)."""
        loop = asyncio.get_running_loop()
        futuros = []
        for evento in eventos:
            futuro = loop.create_future()
            await self.fifo.put((evento, futuro, time.perf_counter()))
            futuros.append(futuro)
        return list(await asyncio.gather(*futuros))

    async def _consumir(self):
        terminar = False
        while not terminar:
            item = await self.fifo.get()
            lote = []
            while True:
                if item is _FIN:
                    terminar = True
                    self.fifo.task_done()
                else:
                    lote.append(item)
                if terminar or len(lote) >= self.lote_maximo or self.fifo.empty():
                    break
                item = self.fifo.get_nowait()
            if lote:
                await self._procesar(lote)

    async def _procesar(self, lote):
        salida = time.perf_counter()
        try:
            resultados = await asyncio.to_thread(self.sistema.recibir_lote, [evento for evento, _, _ in lote])
        except Exception as error:  # el error llega a cada petición; el consumidor sigue vivo
            for _, futuro, _ in lote:
                if not futuro.done():
                    futuro.set_exception(error)
        else:
            self.lotes += 1
            self.eventos += len(lote)
            for (_, futuro, entrada), resultado in zip(lote, resultados):
                resultado['recorrido'] = recorrido(resultado, (salida - entrada) * 1000, len(lote))
                if not futuro.done():
                    futuro.set_result(resultado)
        finally:
            for _ in lote:
                self.fifo.task_done()

    def estadisticas(self):
        return dict(capacidad=self.fifo.maxsize, en_cola=self.fifo.qsize(), pico=self.fifo.peak_size,
                    puts_bloqueados=self.fifo.blocked_puts, lotes=self.lotes, eventos=self.eventos)


def recorrido(resultado, espera_ms, tamano_lote):
    """Etapas que atravesó un evento: 0 (FIFO) y 1 (lote) siempre; las demás según sus servicios."""
    servicios = resultado.get('servicios', [])
    etapas = {0, 1}
    for servicio in servicios:
        etapas.update(ETAPAS_POR_SERVICIO.get(servicio, ()))
    return dict(etapas=sorted(etapas), servicios=servicios, espera_fifo_ms=round(espera_ms, 3),
                tamano_lote=tamano_lote)
