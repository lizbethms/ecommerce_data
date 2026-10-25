"""Un APIRouter por servicio."""
from fastapi import HTTPException, Request


def sistema(request: Request):
    return request.app.state.sistema


def o_404(valor, mensaje='No encontrado'):
    if valor is None:
        raise HTTPException(status_code=404, detail=mensaje)
    return valor
