"""Servicios del sistema; cada uno encapsula sus estructuras."""
from .base import Servicio
from .busqueda import ServicioBusqueda
from .catalogo import ServicioCatalogo
from .cocompra import ServicioCoCompra
from .fraude import ServicioFraude
from .ingesta import ServicioIngesta
from .panel import ServicioPanel
from .priorizacion import ServicioPriorizacion
from .recomendacion import ServicioRecomendacion

__all__ = ['Servicio', 'ServicioBusqueda', 'ServicioCatalogo', 'ServicioCoCompra', 'ServicioFraude',
           'ServicioIngesta', 'ServicioPanel', 'ServicioPriorizacion', 'ServicioRecomendacion']
