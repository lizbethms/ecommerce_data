"""Contrato común de los servicios y utilidades de tiempo."""
from abc import ABC, abstractmethod
from datetime import datetime


def epoch(iso):
    """Segundos UTC desde un ISO con sufijo Z."""
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp()


class Servicio(ABC):
    """Un servicio se suscribe a tipos de evento y aporta su resultado al sobre.

    ``procesar`` recibe el evento ya validado y el ``contexto`` del sobre, donde
    los servicios anteriores dejaron sus resultados. Lo que devuelve queda en
    ``contexto[self.nombre]``.
    """

    nombre = 'servicio'
    tipos = None  # None: todos los tipos

    def __init__(self, config):
        self.config = config
        self.procesados = 0

    def acepta(self, evento):
        return self.tipos is None or evento['event_type'] in self.tipos

    def recibir(self, evento, contexto):
        self.procesados += 1
        return self.procesar(evento, contexto)

    @abstractmethod
    def procesar(self, evento, contexto):
        ...

    def estadisticas(self):
        return {'procesados': self.procesados}
