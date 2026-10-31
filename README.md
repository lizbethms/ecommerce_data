# Ecommerce: estructuras de datos y análisis de eventos

Proyecto sobre eventos de ecommerce de REES46: prepara datos reales y sintéticos, reproduce tráfico y ofrece servicios mediante FastAPI y un dashboard Streamlit.

## Arquitectura del pipeline

El diagrama interactivo está en [docs/arquitectura_pipeline.html](docs/arquitectura_pipeline.html); descárgalo y ábrelo en el navegador. Su especificación editable es [docs/arquitectura_pipeline.json](docs/arquitectura_pipeline.json).

Un evento entra por `POST /eventos/lote` y queda en una FIFO acotada (etapa 0, [canal.py](API_SERVICIOS/canal.py)). Si la cola está llena, la petición espera: es la contrapresión. Un consumidor vacía la cola en lotes. La ingesta valida cada lote, lo ordena y descarta duplicados (etapa 1). Después despacha los eventos, en orden temporal, a los servicios de catálogo, fraude, priorización, co-compra, recomendación, búsqueda y panel, que siempre se recorren en ese orden ([API_SERVICIOS/sistema.py](API_SERVICIOS/sistema.py)). La respuesta de cada evento incluye `recorrido`, con las etapas que atravesó. `data_pipeline.py replay` mide la misma FIFO de forma aislada, leyendo desde un archivo.

### Mapa etapa → código → endpoint

| Etapa | Estructuras y algoritmos | Código | Endpoints |
|---|---|---|---|
| 0. Ingesta y buffer | Cola FIFO acotada con contrapresión | [fifo.py](src/structures/fifo.py); en la API, [canal.py](API_SERVICIOS/canal.py); réplica aislada, [runner.py](src/pipeline/runner.py) | `POST /eventos`, `POST /eventos/lote`; estado de la cola en `GET /admin/estadisticas` |
| 1. Preprocesamiento por lotes | Merge sort; deduplicación por adyacencia y tabla hash | [sorting.py](src/structures/sorting.py), [hash_table.py](src/structures/hash_table.py), [ingesta.py](API_SERVICIOS/servicios/ingesta.py) | `POST /eventos/lote` |
| 2. Cola con prioridades | MinHeap con política EDF; las alertas de fraude van primero | [heap.py](src/structures/heap.py), [priorizacion.py](API_SERVICIOS/servicios/priorizacion.py) | `GET /ordenes/cola`, `POST /ordenes/atender`, `GET /ordenes/{order_id}` |
| 3. Almacenamiento, lookup y caché | Tabla hash, caché LRU, matriz dispersa usuario × producto | [hash_table.py](src/structures/hash_table.py), [lru.py](src/structures/lru.py), [sparse_matrix.py](src/structures/sparse_matrix.py), [catalogo.py](API_SERVICIOS/servicios/catalogo.py) | `GET /productos/{product_id}`, `GET /categorias`, `GET /categorias/{category_id}/productos` |
| 4. Indexación principal | B+Tree (búsqueda binaria en los nodos) por precio, categoría y tiempo de venta | [bplus_tree.py](src/structures/bplus_tree.py), [catalogo.py](API_SERVICIOS/servicios/catalogo.py), [panel.py](API_SERVICIOS/servicios/panel.py) | `GET /productos?precio_min=&precio_max=&categoria=`, `GET /panel/ventas` |
| 5. Índice multidimensional y KNN exacto | KD-Tree | [kd_tree.py](src/structures/kd_tree.py), [recomendacion.py](API_SERVICIOS/servicios/recomendacion.py) | `GET /productos/{product_id}/similares?metodo=knn` |
| 6. Filtrado probabilístico [FIJA] | Bloom Filter, Count-Min Sketch por ventanas, verificación exacta | [bloom.py](src/structures/bloom.py), [count_min.py](src/structures/count_min.py), [fraude.py](API_SERVICIOS/servicios/fraude.py) | `POST /fraude/verificar`, `POST /fraude/senalados`, `GET /fraude/alertas`, `GET /fraude/estadisticas` |
| 7. Similitud aproximada [FIJA] | MinHash + LSH (conjuntos), HNSW (vectores) | [minhash_lsh.py](src/structures/minhash_lsh.py), [hnsw.py](src/structures/hnsw.py), [recomendacion.py](API_SERVICIOS/servicios/recomendacion.py) | `GET /productos/{product_id}/similares?metodo=hnsw` o `metodo=minhash`, `GET /usuarios/{user_id}/recomendaciones` |
| 8. Grafo de dominio [FIJA] | Grafo ponderado de co-compra, PageRank, Louvain y Label Propagation (comparación con NMI y ARI) | [graph.py](src/structures/graph.py), [cocompra.py](API_SERVICIOS/servicios/cocompra.py) | `GET /cocompra/pares`, `GET /cocompra/influyentes`, `GET /cocompra/comunidades?metodo=louvain` o `metodo=label_propagation`, `GET /cocompra/productos/{product_id}/cross-selling`, `GET /productos/{product_id}/complementarios` |
| 9. Servicio y visualización | Trie ponderado, Top-K, API FastAPI, dashboard Streamlit | [trie.py](src/structures/trie.py), [topk.py](src/structures/topk.py), [busqueda.py](API_SERVICIOS/servicios/busqueda.py), [panel.py](API_SERVICIOS/servicios/panel.py), [dashboard/app.py](dashboard/app.py) | `GET /buscar/autocompletar`, `GET /buscar`, `GET /panel` |

## Equipo y roles

| Etapa | Nombre | Bloque | Estructuras y algoritmos | Responsable |
|---|---|---|---|---|
| – | Introducción y contexto del proyecto | – | – | Lizbeth Mamani |
| 0 | Ingesta y buffer | S1 | Cola FIFO acotada para el stream de entrada | Lizbeth Mamani |
| 1 | Preprocesamiento por lotes | S2 | Merge sort y deduplicación por tabla hash | Lizbeth Mamani |
| 2 | Cola con prioridades | S3 | MinHeap con política EDF | Karen Vargas |
| 3 | Almacenamiento, lookup y caché | S4 | Tabla hash, matriz dispersa y caché LRU | Karen Vargas |
| 4 | Indexación principal | S5 | B+Tree | Jhon Campos |
| 5 | Índice multidimensional y KNN exacto | S6 | KD-Tree; KNN exacto como línea base | Jhon Campos |
| 6 [FIJA] | Filtrado probabilístico | S7 | Bloom Filter, Count-Min Sketch y CMS por ventanas | Jhon Campos |
| 7 [FIJA] | Similitud aproximada | S7 | MinHash + LSH y HNSW, frente a fuerza bruta y KNN exacto | Nicolas Trelles |
| 8 [FIJA] | Grafo de dominio | S8–S9 | PageRank; comunidades con Louvain frente a Label Propagation | Nicolas Trelles |
| 9 | Servicio y visualización | Transversal | Top-K, Trie de autocompletado, API y dashboard | Nicolas Trelles |
| – | Conclusiones y resultados | – | – | Nicolas Trelles |

| Integrante | Responsabilidad principal | Aporte concreto |
|---|---|---|
| Lizbeth Mamani Salce | Etapas 0 y 1; introducción | |
| Karen Vargas García | Etapas 2 y 3 | |
| Jhon Campos Arteaga | Etapas 4, 5 y 6 | |
| Nicolas Trelles Vizcarra | Etapas 7, 8 y 9; conclusiones | |

## 1. Instalar y preparar el entorno

Requiere Python 3.11 o superior. Ejecuta los comandos desde la raíz del proyecto.

**Linux / macOS:**

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

**Windows (Git Bash):**

```sh
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
```

Coloca el archivo original `10M.csv` en la raíz del proyecto, no dentro de `data/`. En cada terminal nueva, activa el entorno: `source .venv/bin/activate` en Linux/macOS o `source .venv/Scripts/activate` en Windows. Los scripts de [scripts/ejemplos/](scripts/ejemplos/) detectan el entorno en ambas rutas.

## 2. Generar los datos

Usa los scripts de [scripts/ejemplos/](scripts/ejemplos/). Para seguir esta guía, genera **1K eventos**:

```sh
bash scripts/ejemplos/generar_1K.sh
```

Para otra escala, elige el script correspondiente:

| Eventos | Script |
|---:|---|
| 1.000 | [generar_1K.sh](scripts/ejemplos/generar_1K.sh) |
| 10.000 | [generar_10K.sh](scripts/ejemplos/generar_10K.sh) |
| 100.000 | [generar_100K.sh](scripts/ejemplos/generar_100K.sh) |
| 1.000.000 | [generar_1M.sh](scripts/ejemplos/generar_1M.sh) |
| 10.000.000 | [generar_10M.sh](scripts/ejemplos/generar_10M.sh) |

Los scripts usan [configs/prepare.json](configs/prepare.json). Por defecto, el 20 % de los eventos es sintético; puedes ajustar `synthetic.fraction`, la semilla y otros parámetros por perfil. N incluye los escenarios controlados y los reenvíos.

La salida queda en `data/prepared/perfil_<escala>/`:

- `events.parquet`: eventos para la FIFO, la API y el análisis.
- Otros archivos Parquet y `entities.sqlite`: catálogo, órdenes e inventario, entre otras entidades.
- `manifest.json`: configuración efectiva, conteos, hashes y validaciones.

Si los datos ya están generados, reutiliza su carpeta. Para otra fuente o una nueva corrida:

```sh
bash scripts/ejemplos/generar_1K.sh \
  --source /ruta/datos.csv --output data/prepared/otra_1K
```

Las salidas deben ser nuevas. Si cambias la carpeta, reemplaza `data/prepared/perfil_1K` en los pasos siguientes. Puedes seleccionar otra configuración con `CONFIG=/ruta/config.json` antes de `bash`.

## 3. Medir la FIFO (opcional)

Con el entorno activado:

```sh
python scripts/data_pipeline.py --config configs/replay.json replay \
  --events data/prepared/perfil_1K/events.parquet \
  --output results/flujo_1K/fifo/eventos.jsonl \
  --metrics results/flujo_1K/fifo/metricas.json \
  --mode unlimited
```

Revisa `metricas.json` para ver conteos, throughput, latencia, memoria y ocupación de la cola. Esta ejecución mide la FIFO aislada y escribe un archivo. La API usa la misma `BoundedFIFO` en su ruta de ingesta (paso 5).

## 4. Generar el informe (opcional)

```sh
PYTHONHASHSEED=2026 python scripts/demo_tecnica.py \
  --datos data/prepared/perfil_1K \
  --salida results/flujo_1K/informe \
  --semilla 2026 --k 10 --consultas 10 --repeticiones 100
```

Abre `results/flujo_1K/informe/resumen.md`. La misma carpeta contiene `evidencia.json`, tablas y figuras. Esos valores son los predeterminados.

- `--repeticiones` se aplica a las consultas de similitud, al barrido de parámetros y a PageRank, Louvain y Label Propagation. Con 100 repeticiones, 10M sigue siendo viable.
- La desviación se reporta por consulta (`tablas/similitud_por_consulta.csv`). El resumen separa el ruido de repetir una consulta de la diferencia entre consultas.
- **Barrido de parámetros:** recall@5 y recall@10 frente a latencia, variando `ef` de HNSW (16 a 128) y las bandas × filas de LSH sobre las mismas firmas. Está en `tablas/similitud_barrido_resumen.csv` y en la figura `03b_barrido_similitud`.
- **Comunidades:** Louvain frente a Label Propagation en `tablas/comunidades_comparacion.csv`, con la estabilidad de 10 semillas en `tablas/comunidades_estabilidad.csv` y la figura `06b_comunidades_comparacion`.
- `evidencia.json` registra la plataforma: sistema, CPU, núcleos y RAM. El análisis usa una aplicación aislada y no requiere levantar la API.

### Medir memoria por escala

Con las carpetas preparadas, ejecuta una campaña independiente para Bloom, CMS, CMS por ventanas, HNSW, KD-Tree y MinHash/LSH, junto a sus alternativas exactas:

```sh
python scripts/benchmark_memoria.py \
  --datos data/prepared/perfil_1K data/prepared/perfil_10K data/prepared/perfil_100K \
  --salida results/experimentos/memoria_completa_01 --repeticiones 3
```

Agrega `data/prepared/perfil_1M` y `data/prepared/perfil_10M` a `--datos` cuando existan. El script crea un proceso nuevo por estructura, escala y repetición; guarda `evidencia_memoria.json`, `resumen_memoria.csv`, `resumen_memoria.md` y figuras. La carpeta de salida debe ser nueva. Las claves de fraude proceden de los intentos de pago, incluidos reenvíos. Los vectores de 19 dimensiones se derivan del catálogo sin popularidad dinámica; los conjuntos se forman con vistas, carritos y compras. Cada comparación usa el mismo input dentro de su familia. El informe registra eventos y tamaño real de cada índice. La memoria Python incremental excluye los datos de entrada; el pico RSS cubre el proceso completo.

Para incorporar esa comparación al informe de 1K ya generado, sin repetir sus consultas:

```sh
python scripts/demo_tecnica.py \
  --evidencia results/flujo_1K/informe/evidencia.json \
  --memoria results/experimentos/memoria_completa_01/evidencia_memoria.json
```

También puedes pasar `--memoria` al generar un informe nuevo. Esto añade la sección y las figuras de memoria; las repeticiones de memoria se ejecutan únicamente con `benchmark_memoria.py`.

El informe incluye un resumen del monitor al terminar esa reproducción: ingesta, eventos aceptados por tipo y origen, alertas de pago, ventas y cola. Las alertas son órdenes señaladas para revisión o bloqueo, no fraudes confirmados. La sección de fraude distingue alertas por orden de decisiones por intento de pago.

### Medir tiempos por escala

Mide la construcción y una operación típica de cada estructura del pipeline, con su carga real en cada escala. También compara Bloom y CMS con sus alternativas exactas en tiempo, falsos positivos y error de frecuencia:

```sh
python scripts/benchmark_tiempos.py \
  --datos data/prepared/perfil_1K data/prepared/perfil_10K data/prepared/perfil_100K \
  --salida results/experimentos/tiempos_01
```

- Cada caso corre en un proceso nuevo, con la entrada cargada antes de cronometrar.
- La operación se repite 100 veces sobre un lote fijo de consultas (`--repeticiones`). La construcción completa se repite 3 veces (`--repeticiones-construccion`), porque en 1M y 10M es la parte cara.
- Agrega `perfil_1M` y `perfil_10M` a `--datos` para la campaña completa; `--casos` limita las estructuras.
- La carpeta de salida debe ser nueva. Guarda `evidencia_tiempos.json` y `resumen_tiempos.md`.
- Las tablas incluyen `tiempos_pendientes.csv` (exponente log-log observado frente al esperado), `probabilisticas_vs_exactas.csv`, `calidad_bloom.csv` y `calidad_cms.csv`.
- Las figuras son `tiempos_construccion`, `tiempos_operacion` y `calidad_probabilisticas`.

Corre todas las campañas en la misma máquina para que los tiempos sean comparables.

## 5. Iniciar la API, el dashboard y el tráfico

Abre **tres terminales** desde la raíz del proyecto. Los tres comandos usan los datos del paso 2.

**Terminal 1 — API:**

```sh
source .venv/bin/activate   # Windows: source .venv/Scripts/activate
ECOMMERCE_DATOS=data/prepared/perfil_1K PRECARGAR=0 \
  python -m uvicorn API_SERVICIOS.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — dashboard:**

```sh
source .venv/bin/activate   # Windows: source .venv/Scripts/activate
ECOMMERCE_API_URL=http://127.0.0.1:8000 \
  python -m streamlit run dashboard/app.py --server.port 8501
```

**Terminal 3 — enviar eventos:**

Cuando la API esté lista y tengas abierto el dashboard, ejecuta:

```sh
source .venv/bin/activate   # Windows: source .venv/Scripts/activate
python -m API_SERVICIOS.cliente_trafico \
  --eventos data/prepared/perfil_1K/events.parquet \
  --url http://127.0.0.1:8000 \
  --lote 20 --tasa 100 --reenvios 0 --invalidos 0
```

| Interfaz | Dirección |
|---|---|
| Dashboard: ingesta, ventas, cola y fraude | <http://localhost:8501> |
| Swagger: consultar y probar los servicios | <http://127.0.0.1:8000/docs> |
| Estado de la API | <http://127.0.0.1:8000/salud> |

El dashboard consulta la API periódicamente; el cliente es quien envía el tráfico. El archivo ya puede contener duplicados, por lo que los eventos aceptados pueden ser menos que N. Para repetir desde cero, detén la API con `Ctrl+C`, vuelve a iniciarla y ejecuta otra vez el cliente. Mantén `PRECARGAR=0` en este flujo para enviar el archivo una sola vez.

Para comparar el dashboard con el informe, usa el **mismo** `events.parquet` y espera a que termine el cliente. Comprueba la carpeta indicada en el dashboard, los eventos aceptados, duplicados y rechazados, y luego las alertas y ventas. El informe es una captura de una API aislada; el dashboard es una vista del servidor actual. Los conteos del archivo incluyen duplicados, mientras que las gráficas de actividad del dashboard cuentan solo eventos aceptados. La prueba de idempotencia del informe reenvía una compra al final y añade un duplicado únicamente a las estadísticas finales de `evidencia.json`.

Si generaste el informe con otra escala, usa la misma carpeta `data/prepared/perfil_<escala>` al iniciar la API y al enviar eventos.

### Ver una orden atravesar las diez etapas

```sh
python scripts/recorrido_evento.py --datos data/prepared/perfil_1K
```

El script levanta la API en su propio proceso, envía `events.parquet` y luego una orden: un intento de pago fallido y dos compras. El pago pasa por fraude (etapa 6) y las compras por el grafo (etapa 8); juntos recorren las etapas 0–9. Para cada etapa imprime una salida observable:

| Etapa | Salida |
|---|---|
| 0 | Ocupación de la FIFO |
| 1 | Deduplicación de un reenvío |
| 2 | Posición en el heap |
| 3 | Fallo y acierto de la caché LRU |
| 4 | Ventas por rango en el B+Tree |
| 5 | KNN exacto con KD-Tree |
| 6 | Alerta de fraude |
| 7 | Recall de HNSW |
| 8 | Cross-selling |
| 9 | Autocompletado y Top-K |

Con `--url http://127.0.0.1:8000` usa la API de la Terminal 1, que ya tiene tráfico. Con `--salida archivo.json` guarda las respuestas.

La preparación trabaja por bloques; la API y el análisis mantienen estado en memoria. Usa 1K para esta demostración: generar 1M o 10M no garantiza que todas las etapas puedan procesarlos con la misma memoria.

## 6. Verificar la API y graficar el informe final (opcional)

**Verificación funcional de la API.** Inicia la API como en la Terminal 1 del paso 5, pero **no** ejecutes el cliente de tráfico: el script envía los eventos por su cuenta. Después compara ventas, stock y co-compra con el Parquet:

```sh
python scripts/verificar_api_funcional.py \
  --datos data/prepared/perfil_1K \
  --salida results/flujo_1K/api_funcional.json
```

Indica siempre `--datos`, porque el valor por defecto apunta a una carpeta antigua. El JSON de evidencia se guarda aunque alguna comprobación falle.

**Figuras log-log del informe final.** [scripts/graficar_informe_final.py](scripts/graficar_informe_final.py) no ejecuta benchmarks: lee resultados ya guardados. Antes necesita:

- los informes del paso 4 para 1K, 10K, 100K y 1M, en `results/flujo_<escala>/informe/`;
- la campaña de memoria en `results/experimentos/memoria_completa_01/`.

```sh
python scripts/graficar_informe_final.py
```

Guarda `escalabilidad_consulta.pdf` y `escalabilidad_memoria.pdf` en `docs/informe_figuras/`.

## Pruebas y referencias

Para ejecutar las pruebas:

```sh
python -m unittest discover -s tests -v
```

- [Diagrama de arquitectura](docs/arquitectura_pipeline.html): componentes, etapas y recorrido de un evento.
- [Dashboard](dashboard/README.md): opciones de la interfaz y actualización.
- [Configuración de preparación](configs/prepare.json) y [reproducción](configs/replay.json).
