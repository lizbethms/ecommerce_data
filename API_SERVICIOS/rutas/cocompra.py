"""Co-compra: pares, productos influyentes y comunidades."""
from fastapi import APIRouter, Depends, Query

from . import o_404, sistema

router = APIRouter(prefix='/cocompra', tags=['Co-compra'])


@router.get('/pares', summary='Pares de productos más comprados juntos')
def pares(k: int = Query(10, ge=1, le=200), s=Depends(sistema)):
    with s.lock:
        return s.cocompra.pares(k)


@router.get('/influyentes', summary='Productos influyentes (PageRank ponderado)')
def influyentes(k: int = Query(10, ge=1, le=200), s=Depends(sistema)):
    with s.lock:
        return [dict(i, nombre=(s.catalogo.registro(i['product_id']) or {}).get('nombre'))
                for i in s.cocompra.influyentes(k)]


@router.get('/comunidades', summary='Agrupaciones de consumo (Louvain)')
def comunidades(min_tamano: int = Query(3, ge=1), limite: int = Query(20, ge=1, le=500), s=Depends(sistema)):
    with s.lock:
        return s.cocompra.comunidades(min_tamano, limite)


@router.get('/productos/{product_id}/cross-selling', summary='Cross-selling para un producto')
def cross_selling(product_id: str, k: int = Query(10, ge=1, le=100), s=Depends(sistema)):
    with s.lock:
        o_404(s.catalogo.registro(product_id), 'Producto no encontrado')
        return {'product_id': product_id, 'comunidad': s.cocompra.comunidad_de(product_id),
                'sugerencias': s.recomendacion.complementarios(product_id, k)}
