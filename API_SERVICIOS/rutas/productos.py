"""Consulta de productos y productos relacionados."""
from typing import Literal

from fastapi import APIRouter, Depends, Query

from . import o_404, sistema

router = APIRouter(tags=['Productos'])


@router.get('/productos', summary='Consulta por rango de precio y/o prefijo de categoría')
def rango(precio_min: float | None = Query(None, ge=0), precio_max: float | None = Query(None, ge=0),
          categoria: str | None = Query(None, description='Prefijo de category_code, p. ej. electronics.smartphone'),
          category_id: str | None = None, solo_disponibles: bool = False,
          limite: int = Query(50, ge=1, le=1000), s=Depends(sistema)):
    with s.lock:
        resultados = s.catalogo.rango(precio_min, precio_max, categoria, category_id, solo_disponibles, limite)
    return {'total': len(resultados), 'resultados': resultados}


@router.get('/productos/{product_id}', summary='Consulta puntual (hash + caché LRU)')
def producto(product_id: str, s=Depends(sistema)):
    with s.lock:
        return o_404(s.catalogo.obtener(product_id), 'Producto no encontrado')


@router.get('/categorias', summary='Categorías y número de productos')
def categorias(nivel: int | None = Query(None, ge=1, le=4), s=Depends(sistema)):
    with s.lock:
        return s.catalogo.categorias(nivel)


@router.get('/categorias/{category_id}/productos', summary='Productos de un category_id')
def por_categoria(category_id: str, limite: int = Query(50, ge=1, le=1000), s=Depends(sistema)):
    with s.lock:
        return s.catalogo.por_categoria(category_id, limite)


@router.get('/productos/{product_id}/similares', tags=['Productos relacionados'],
            summary='Similares por atributos (knn exacto / hnsw) o por comportamiento (minhash)')
def similares(product_id: str, metodo: Literal['hnsw', 'knn', 'minhash'] = 'hnsw',
              k: int = Query(10, ge=1, le=100), s=Depends(sistema)):
    with s.lock:
        return o_404(s.recomendacion.similares(product_id, k, metodo), 'Producto no encontrado')


@router.get('/productos/{product_id}/complementarios', tags=['Productos relacionados'],
            summary='Complementarios a partir de la co-compra')
def complementarios(product_id: str, k: int = Query(10, ge=1, le=100), s=Depends(sistema)):
    with s.lock:
        o_404(s.catalogo.registro(product_id), 'Producto no encontrado')
        return s.recomendacion.complementarios(product_id, k)


@router.get('/usuarios/{user_id}/recomendaciones', tags=['Productos relacionados'],
            summary='Recomendaciones híbridas para un usuario')
def recomendaciones(user_id: str, k: int = Query(10, ge=1, le=100), s=Depends(sistema)):
    with s.lock:
        return s.recomendacion.para_usuario(user_id, k)
