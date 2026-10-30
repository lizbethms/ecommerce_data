"""Aplicación FastAPI. Ejecutar desde la raíz del repo:

    uvicorn API_SERVICIOS.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Config
from .rutas import cocompra, eventos, fraude, ordenes, productos, servicio, sistema
from .sistema import SistemaEcommerce


def create_app(config=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.sistema = SistemaEcommerce.desde_config(config or Config())
        yield

    app = FastAPI(title='API de servicios de comercio electrónico', version='1.0', lifespan=lifespan,
                  description='''Demo técnica de comercio electrónico. El guion y la
ejecución reproducible están documentados en `README.md` y `notebooks/01_demo_tecnica.ipynb`.

**Recorrido sugerido (3–4 minutos):**
1. Prioridades: `POST /eventos/lote` → `GET /ordenes/cola` → `POST /ordenes/atender`.
2. Filtrado probabilístico: `/fraude/senalados`, `/fraude/verificar` y `/fraude/estadisticas`.
   Los positivos y las estimaciones se verifican con registros exactos.
3. Similitud: comparar `knn`, `hnsw` y `minhash` en `/productos/{id}/similares`.
   El endpoint HNSW también ejecuta KD-Tree; su latencia no mide HNSW puro.
4. Grafo: `/cocompra/pares`, `/cocompra/influyentes` y `/cocompra/comunidades`.
   Los productos son nodos; los pares son aristas y el peso cuenta órdenes distintas.
   V y E son resultados del tráfico, no se igualan al número de eventos.
5. Servicio: `/buscar/autocompletar`, `/buscar`, recomendaciones y `/panel`.

El estado reside en memoria. Reiniciar la API restablece el estado; atender órdenes
consume la cola. El notebook utiliza una aplicación aislada y exporta JSON, tablas
y figuras sin modificar un servidor que ya esté corriendo.
''')
    for modulo in (eventos, ordenes, productos, fraude, cocompra, servicio):
        app.include_router(modulo.router)

    @app.exception_handler(ValueError)
    async def valor_invalido(request: Request, error: ValueError):
        return JSONResponse(status_code=400, content={'detail': str(error)})

    @app.get('/salud', tags=['Administración'])
    def salud(s=Depends(sistema)):
        return {'estado': 'ok', 'carga': s.carga, 'productos': len(s.catalogo.productos),
                'eventos_aceptados': s.ingesta.aceptados}

    @app.get('/admin/estadisticas', tags=['Administración'])
    def estadisticas(s=Depends(sistema)):
        return s.estadisticas()

    @app.post('/admin/reconstruir', tags=['Administración'], summary='Forzar reconstrucción de KD-Tree, HNSW y LSH')
    def reconstruir(s=Depends(sistema)):
        with s.lock:
            s.recomendacion.reconstruir(forzar=True)
            return s.recomendacion.estadisticas()

    return app


app = create_app()
