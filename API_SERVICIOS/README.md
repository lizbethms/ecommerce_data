# API_SERVICIOS: demo funcional

Una API FastAPI recibe tráfico con la estructura de `data/prepared_5K/events.parquet` y expone los servicios del enunciado. Cada servicio es una clase (`servicios/`) que hereda de `Servicio` y usa estructuras propias de `src/structures/`, implementadas desde cero.

## Ejecutar (desde la raíz del repo)

```sh
pip install -r requirements.txt
python scripts/stage0.py --config configs/sample.json sample --output data/prepared_5K   # si aún no existe
uvicorn API_SERVICIOS.main:app --reload            # documentación interactiva en http://127.0.0.1:8000/docs
python -m API_SERVICIOS.cliente_trafico --lote 250 --reenvios 0.02 --invalidos 0.01
```

- Al arrancar, la API carga catálogo, inventario y señalados desde los Parquet. El resto del estado se construye con el tráfico que llega.
- `PRECARGAR=1` reproduce además `events.parquet` al iniciar.
- `ECOMMERCE_DATOS=<carpeta>` indica otra preparación.

## Flujo de un evento

```text
POST /eventos[/lote]
  → ServicioIngesta: normaliza (UTC, Decimal, ids texto), valida con src/data/schema.py,
    ordena el lote (merge sort) y descarta reenvíos (event_id + huella de contenido en HashTable)
  → sobre {contexto} por los suscriptores, en orden temporal:
    Catálogo → Fraude → Priorización → CoCompra → Recomendación → Búsqueda → Panel
```

La respuesta trae, por evento, `aceptado | duplicado | rechazado(motivo)` y el resultado de cada servicio.

| Servicio | Estructuras | Endpoints |
|---|---|---|
| Ingesta | `merge_sort`, `HashTable` | `POST /eventos`, `POST /eventos/lote` |
| Priorización | `MinHeap` con clave (clase, plazo, llegada): primero alertas, luego órdenes por plazo (EDF). Express vence a +4 h, estándar a +48 h y programada en `scheduled_at` | `GET /ordenes/cola`, `POST /ordenes/atender`, `GET /ordenes/{id}` |
| Catálogo | `HashTable` + `LRUCache` (consulta puntual); `BPlusTree` por precio y por `category_code` (rangos) | `GET /productos/{id}`, `GET /productos?precio_min&precio_max&categoria`, `GET /categorias` |
| Relacionados | `KDTree` (KNN exacto), `HNSW` (aproximado, informa recall@k frente al exacto), `SparseMatrix` + `MinHash`/`LSH` (comportamiento) | `GET /productos/{id}/similares?metodo=knn\|hnsw\|minhash`, `/complementarios`, `GET /usuarios/{id}/recomendaciones` |
| Fraude | `BloomFilter` + verificación exacta; `WindowedCMS` + conteo exacto de la ventana antes de bloquear | `POST /fraude/verificar`, `GET /fraude/alertas`, `POST /fraude/senalados`, `GET /fraude/estadisticas` |
| Co-compra | `WeightedGraph` (peso = órdenes distintas), `pagerank`, `louvain` | `GET /cocompra/pares`, `/influyentes`, `/comunidades`, `/productos/{id}/cross-selling` |
| Servicio | `Trie` ponderado, `top_k`; ventas en `BPlusTree` por tiempo | `GET /buscar/autocompletar`, `GET /buscar?orden=relevancia\|popularidad`, `GET /panel`, `GET /panel/ventas` |

Administración: `GET /salud`, `GET /admin/estadisticas`, `POST /admin/reconstruir`.

## Decisiones y límites

- **Idempotencia.** Un reenvío (mismo `event_id` y contenido) no vuelve a contar compras, stock ni aristas. Si el `event_id` coincide pero el contenido es distinto, el evento se rechaza. La etiqueta `is_injected_duplicate` nunca se consulta.
- **Prioridad.** Sigue la regla explícita de `POLICIES['priority']`: pago fallido = 100, express = 10 y el resto 0. Se recalcula en la ingesta y no confía en el valor que manda el cliente.
- **Fraude.** Un positivo del Bloom solo cuenta tras verificarlo en el registro exacto. Si el CMS supera el umbral (5 intentos en 600 s), se confirma con el conteo exacto antes de bloquear. Las órdenes bloqueadas quedan retenidas al atenderlas. Las etiquetas de anomalía sirven solo para evaluar la simulación.
- **Stock.** Es sintético: `supplied` del inventario preparado más `stock_base` (10), al que el tráfico resta compras y suma devoluciones.
- **Índices.** KD-Tree, HNSW y LSH se reconstruyen en diferido (si hubo cambios y pasaron 30 s) o con `/admin/reconstruir`. PageRank y Louvain se recalculan solo si cambió el grafo.
- **Concurrencia.** El estado vive en memoria, en un solo proceso, y un `RLock` serializa las operaciones. El B+Tree también es en memoria; la versión en disco y las mediciones de escala quedan para los benchmarks.
