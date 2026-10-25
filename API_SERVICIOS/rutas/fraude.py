"""Posible fraude: verificación de pertenencia, intensidad y alertas."""
from typing import Literal

from fastapi import APIRouter, Depends, Query

from ..modelos import ConsultaFraude
from ..servicios.base import epoch
from . import sistema

router = APIRouter(prefix='/fraude', tags=['Fraude'])


@router.post('/verificar', summary='Evaluar cuenta/dispositivo/medio sin registrar un intento')
def verificar(consulta: ConsultaFraude, s=Depends(sistema)):
    with s.lock:
        ts = epoch(consulta.event_time) if consulta.event_time else None
        return s.fraude.evaluar(consulta.user_id, consulta.device_id, consulta.payment_method_id, ts, registrar=False)


@router.get('/alertas', summary='Alertas generadas (más recientes primero)')
def alertas(decision: Literal['bloquear', 'revisar'] | None = None, limite: int = Query(50, ge=1, le=1000),
            s=Depends(sistema)):
    with s.lock:
        return s.fraude.lista_alertas(decision, limite)


@router.post('/senalados', summary='Señalar una cuenta, dispositivo o medio de pago')
def senalar(tipo: Literal['account', 'device', 'payment_method'], valor: str, motivo: str = 'manual',
            s=Depends(sistema)):
    with s.lock:
        return {'clave': s.fraude.senalar(tipo, valor, motivo), 'senalados': len(s.fraude.senalados)}


@router.get('/estadisticas', summary='Bloom, CMS y decisiones')
def estadisticas(s=Depends(sistema)):
    with s.lock:
        return s.fraude.estadisticas()
