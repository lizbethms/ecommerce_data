"""Priorización de órdenes y alertas."""
from fastapi import APIRouter, Depends, Query

from . import o_404, sistema

router = APIRouter(prefix='/ordenes', tags=['Priorización'])


@router.get('/cola', summary='Próximos elementos de la cola (sin extraerlos)')
def cola(n: int = Query(20, ge=1, le=500), s=Depends(sistema)):
    with s.lock:
        return {'en_cola': len(s.priorizacion.heap), 'siguientes': s.priorizacion.cola(n)}


@router.post('/atender', summary='Extraer y atender los n elementos más urgentes')
def atender(n: int = Query(1, ge=1, le=500), s=Depends(sistema)):
    with s.lock:
        return {'atendidos': s.priorizacion.atender(n), 'en_cola': len(s.priorizacion.heap)}


@router.get('/{order_id}', summary='Estado de una orden')
def orden(order_id: str, s=Depends(sistema)):
    with s.lock:
        return o_404(s.priorizacion.estado_orden(order_id), 'Orden no encontrada')
