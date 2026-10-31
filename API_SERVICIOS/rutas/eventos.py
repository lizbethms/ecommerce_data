"""Ingesta de tráfico con la estructura de events.parquet."""
from fastapi import APIRouter, Depends, HTTPException

from ..modelos import EventoIn
from . import canal

router = APIRouter(prefix='/eventos', tags=['Ingesta'])
MAX_LOTE = 5000


@router.post('', summary='Recibir un evento (pasa por la FIFO de ingesta)')
async def recibir(evento: EventoIn, c=Depends(canal)):
    return (await c.enviar([evento.model_dump()]))[0]


@router.post('/lote', summary='Recibir un lote: FIFO acotada, orden y deduplicación, y despacho en orden temporal')
async def recibir_lote(eventos: list[EventoIn], c=Depends(canal)):
    if len(eventos) > MAX_LOTE:
        raise HTTPException(status_code=413, detail=f'Máximo {MAX_LOTE} eventos por lote')
    resultados = await c.enviar([e.model_dump() for e in eventos])
    resumen = {}
    for r in resultados:
        resumen[r['estado']] = resumen.get(r['estado'], 0) + 1
    return {'resumen': resumen, 'resultados': resultados}
