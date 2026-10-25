"""Ingesta de tráfico con la estructura de events.parquet."""
from fastapi import APIRouter, Depends, HTTPException

from ..modelos import EventoIn
from . import sistema

router = APIRouter(prefix='/eventos', tags=['Ingesta'])
MAX_LOTE = 5000


@router.post('', summary='Recibir un evento')
def recibir(evento: EventoIn, s=Depends(sistema)):
    return s.recibir(evento.model_dump())


@router.post('/lote', summary='Recibir un lote (se ordena, deduplica y procesa en orden temporal)')
def recibir_lote(eventos: list[EventoIn], s=Depends(sistema)):
    if len(eventos) > MAX_LOTE:
        raise HTTPException(status_code=413, detail=f'Máximo {MAX_LOTE} eventos por lote')
    resultados = s.recibir_lote([e.model_dump() for e in eventos])
    resumen = {}
    for r in resultados:
        resumen[r['estado']] = resumen.get(r['estado'], 0) + 1
    return {'resumen': resumen, 'resultados': resultados}
