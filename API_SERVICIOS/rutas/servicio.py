"""Servicio al usuario: autocompletado, búsqueda y panel."""
from typing import Literal

from fastapi import APIRouter, Depends, Query

from . import sistema

router = APIRouter(tags=['Servicio'])


@router.get('/buscar/autocompletar', summary='Sugerencias por prefijo (Trie ponderado)')
def autocompletar(prefijo: str = Query(..., min_length=1), k: int = Query(10, ge=1, le=50), s=Depends(sistema)):
    with s.lock:
        return s.busqueda.autocompletar(prefijo, k)


@router.get('/buscar', summary='Búsqueda ordenada por relevancia o popularidad')
def buscar(q: str = Query(..., min_length=1), orden: Literal['relevancia', 'popularidad'] = 'relevancia',
           k: int = Query(20, ge=1, le=200), s=Depends(sistema)):
    with s.lock:
        return s.busqueda.buscar(q, orden, k)


@router.get('/panel', summary='Panel de ventas, actividad, alertas y cola')
def panel(minutos: int = Query(30, ge=1, le=1440), k: int = Query(5, ge=1, le=50), s=Depends(sistema)):
    with s.lock:
        return s.panel.resumen(minutos, k)


@router.get('/panel/ventas', summary='Ventas en un rango de fechas (B+Tree por tiempo)')
def ventas(desde: str = Query(..., examples=['2019-10-01T00:00:00Z']),
           hasta: str = Query(..., examples=['2019-10-02T00:00:00Z']), s=Depends(sistema)):
    with s.lock:
        return s.panel.ventas_rango(desde, hasta)
