"""Parámetros de la API. Variables de entorno: ECOMMERCE_DATOS, PRECARGAR."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import RAIZ


def _ruta_datos():
    valor = os.environ.get('ECOMMERCE_DATOS')
    return Path(valor) if valor else RAIZ / 'data' / 'prepared_5K'


@dataclass
class Config:
    dir_datos: Path | None = field(default_factory=_ruta_datos)
    precargar: bool = field(default_factory=lambda: os.environ.get('PRECARGAR', '0') == '1')
    tamano_lote: int = 512

    # Catálogo
    lru_capacidad: int = 256
    orden_bplus: int = 32
    stock_base: int = 10  # supuesto de demo: stock sintético adicional por producto

    # Priorización (horas hasta el compromiso de entrega)
    plazo_express_h: float = 4
    plazo_standard_h: float = 48

    # Fraude
    ventana_fraude_seg: int = 600
    sub_ventanas: int = 6
    umbral_intentos: int = 5
    bloom_fp: float = 0.01
    cms_ancho: int = 1024
    cms_profundidad: int = 4

    # Similitud y recomendación
    k_por_defecto: int = 10
    minhash_permutaciones: int = 64
    lsh_bandas: int = 16
    hnsw_m: int = 8
    hnsw_ef: int = 48
    reconstruir_cada_seg: float = 30.0
    pesos_interaccion: dict = field(default_factory=lambda: {
        'view': 1.0, 'cart': 3.0, 'purchase': 5.0, 'return': -3.0, 'review': 1.0, 'search': 0.0})

    semilla: int = 2026
