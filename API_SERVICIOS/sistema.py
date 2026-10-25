"""Composición de servicios: un sobre por evento recorre los suscriptores en orden."""
import threading
import time
from pathlib import Path

from src.data.parquet_io import iter_events, iter_rows

from .config import Config
from .servicios import (ServicioBusqueda, ServicioCatalogo, ServicioCoCompra, ServicioFraude, ServicioIngesta,
                        ServicioPanel, ServicioPriorizacion, ServicioRecomendacion)


class SistemaEcommerce:
    def __init__(self, config=None):
        self.config = config or Config()
        c = self.config
        self.catalogo = ServicioCatalogo(c)
        self.fraude = ServicioFraude(c)
        self.priorizacion = ServicioPriorizacion(c, self.fraude)
        self.cocompra = ServicioCoCompra(c)
        self.recomendacion = ServicioRecomendacion(c, self.catalogo, self.cocompra)
        self.busqueda = ServicioBusqueda(c, self.catalogo)
        self.panel = ServicioPanel(c, self.catalogo, self.fraude, self.priorizacion)
        # El orden importa: catálogo antes que búsqueda (popularidad) y fraude antes
        # que priorización (las alertas entran a la cola).
        self.ingesta = ServicioIngesta(c, [self.catalogo, self.fraude, self.priorizacion, self.cocompra,
                                           self.recomendacion, self.busqueda, self.panel])
        self.panel.ingesta = self.ingesta
        self.lock = threading.RLock()  # los endpoints síncronos corren en un pool de hilos
        self.carga = {}

    @classmethod
    def desde_config(cls, config=None):
        sistema = cls(config)
        if sistema.config.dir_datos and Path(sistema.config.dir_datos).exists():
            sistema.cargar(sistema.config.dir_datos, sistema.config.precargar)
        return sistema

    def cargar(self, directorio, precargar=False):
        """Catálogo, inventario y señalados desde Parquet; opcionalmente reproduce events.parquet."""
        directorio = Path(directorio)
        inicio = time.perf_counter()
        with self.lock:
            self.catalogo.cargar_catalogo(iter_rows(directorio / 'catalog.parquet'))
            if (directorio / 'inventory.parquet').exists():
                self.catalogo.cargar_inventario(iter_rows(directorio / 'inventory.parquet'))
            if (directorio / 'flags.parquet').exists():
                self.fraude.cargar_senalados(iter_rows(directorio / 'flags.parquet'))
            self.busqueda.indexar_catalogo()
            eventos = 0
            if precargar:
                lote = []
                for evento in iter_events(directorio / 'events.parquet'):
                    lote.append(evento)
                    if len(lote) >= self.config.tamano_lote:
                        self.ingesta.recibir_lote(lote)
                        eventos += len(lote)
                        lote = []
                if lote:
                    self.ingesta.recibir_lote(lote)
                    eventos += len(lote)
        self.carga = dict(directorio=str(directorio), productos=len(self.catalogo.productos),
                          senalados=len(self.fraude.senalados), eventos_precargados=eventos,
                          segundos=round(time.perf_counter() - inicio, 3))
        return self.carga

    def recibir(self, evento):
        with self.lock:
            return self.ingesta.recibir_lote([evento])[0]

    def recibir_lote(self, eventos):
        with self.lock:
            return self.ingesta.recibir_lote(eventos)

    def estadisticas(self):
        with self.lock:
            servicios = (self.ingesta, self.catalogo, self.fraude, self.priorizacion, self.cocompra,
                         self.recomendacion, self.busqueda)
            return {'carga': self.carga, **{s.nombre: s.estadisticas() for s in servicios}}
