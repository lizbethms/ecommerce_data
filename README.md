# Ecommerce: estructuras de datos y análisis de eventos

Proyecto de Estructuras de Datos y Algoritmos sobre eventos de ecommerce de REES46. Prepara datos reproducibles, simula tráfico y ofrece una API FastAPI con catálogo, prioridades, detección de actividad sospechosa, similitud, co-compra, búsqueda y recomendaciones. Las estructuras se implementan en Python y el análisis produce evidencia JSON, tablas CSV/Markdown y figuras PNG/SVG/PDF.

## Organización y responsabilidades

```text
API_SERVICIOS/             API, modelos HTTP, rutas y servicios del dominio
configs/                  Configuración de preparación, muestreo y reproducción
src/
  data/                   Contrato, validación, muestreo, enriquecimiento y Parquet
  structures/             Estructuras de datos y algoritmos compartidos
  pipeline/               Coordinación asíncrona, reloj de reproducción y FIFO
  analysis/               Consultas, referencias exactas, métricas y reportes
scripts/                  Puntos de entrada de las corridas y verificadores
notebooks/                Exploración y lectura de evidencia persistida
tests/                    Pruebas de estructuras, preparación, API y análisis
docs/                     Planes de diseño y experimentación
10M.csv                   Fuente original local, excluida de Git
data/                    Muestras y datos preparados locales
results/                  Salidas regenerables, una carpeta por corrida
```

`API_SERVICIOS/` conserva su ubicación y sus imports públicos. Los servicios dependen del contrato de `src/data/` y de las estructuras de `src/structures/`. El análisis consume esos módulos y la API; los notebooks importan la implementación y los scripts coordinan las ejecuciones.

Las clases de servicios, índices, generador y reloj conservan responsabilidades y estado propios. La FIFO añade capacidad obligatoria y métricas de contrapresión a `asyncio.Queue`. Se eliminó la clase auxiliar `Queries`: el registro de consultas se resuelve con una función y una lista explícita de evidencia. Se reutiliza una única función `digest_file` para calcular hashes.

Este es el único `README.md` y la guía central de ejecución. Los planes de diseño y experimentación se conservan como documentos especializados: [plan del proyecto](docs/plan_proyecto.md) y [plan de experimentación](docs/plan_experimentacion.md). Incluyen trabajo pendiente y no certifican su implementación.

## Instalación y datos

Requiere Python 3.11 o superior. Ejecutar los comandos desde la raíz del repositorio:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` reúne las dependencias del pipeline, la API, el análisis y los notebooks. `prepare` y `replay` en JSONL usan la biblioteca estándar; las pruebas de Parquet, API y reportes usan las dependencias instaladas.

Obtener el dataset REES46 por el mecanismo de distribución permitido y colocar `10M.csv` en la raíz. No se descarga ni redistribuye la fuente. También se puede indicar otra ubicación con `--source /ruta/10M.csv`. La fuente se abre solo en lectura.

Las preparaciones y corridas necesitan **salidas nuevas**. Si una ruta de ejemplo ya existe, cambiar su nombre; no reutilizar carpetas con resultados anteriores. Cada manifiesto conserva configuración, semilla, composición, validaciones y hashes. Los archivos generados y el entorno local se excluyen de Git.

## Corrida de análisis: muestra, consultas, tablas y figuras

### 1. Preparar la muestra

```sh
python scripts/data_pipeline.py --config configs/sample.json sample \
  --source 10M.csv --output data/prepared_5K
```

Este paso copia 5.000 filas originales en `data/sample_5K.csv`, seleccionando sesiones completas dentro de la ventana inicial de un millón de filas y priorizando sesiones con compras. Añade escenarios sintéticos reproducibles y prepara:

| Archivo en `data/prepared_5K/` | Contenido |
|---|---|
| `events.parquet` | Eventos normalizados y enriquecidos |
| `catalog.parquet` | Productos y atributos observados |
| `orders.parquet`, `purchases.parquet` | Órdenes derivadas y compras |
| `inventory.parquet` | Inventario sintético |
| `payments.parquet`, `flags.parquet` | Pagos y señalados sintéticos |
| `entities.sqlite`, `manifest.json` | Entidades, trazabilidad y validaciones |

La muestra final tiene **más de 5.000 eventos** por los escenarios añadidos; consultar el conteo real en el manifiesto. No representa la distribución global del histórico. Para repetir el muestreo, indicar también otro `--csv-output`, por ejemplo `--csv-output data/sample_ensayo02.csv --output data/prepared_ensayo02`.

### 2. Ejecutar el análisis

```sh
PYTHONHASHSEED=2026 python scripts/demo_tecnica.py \
  --datos data/prepared_5K \
  --salida results/demo_tecnica/ensayo_01 \
  --semilla 2026 --k 5 --consultas 5 --repeticiones 5
```

Sin `--salida`, crea una carpeta nueva con fecha UTC en `results/demo_tecnica/`. Usa HTTP ASGI en proceso mediante `TestClient`; no requiere iniciar Uvicorn. Cada corrida crea aplicaciones aisladas y reproduce todo el archivo por lotes de 250. Los escenarios controlados de prioridades y fraude se ejecutan separados del tráfico usado para analizar el grafo.

Las consultas se repiten sobre índices fijos; `--repeticiones` no representa reconstrucciones independientes ni corridas completas. Este ejecutor está pensado para muestras pequeñas; las cinco escalas y la campaña estadística completa se describen en el plan de experimentación.

### 3. Leer y reutilizar los resultados

| Salida de la corrida | Uso |
|---|---|
| `evidencia.json` | Configuración, hashes, entorno, consultas/respuestas y mediciones crudas |
| `resumen.md` | Tablas, figuras, conclusiones y límites del piloto |
| `escenario_prioridades.json` | Eventos sintéticos reutilizables en la API |
| `tablas/*.csv`, `tablas/*.md` | Datos para análisis e informe |
| `figuras/*.png`, `*.svg`, `*.pdf` | Figuras exportables |
| `figuras/pies.md` | Pies de figura y alcance de cada visualización |

Para regenerar tablas y figuras desde la evidencia guardada, sin repetir las consultas:

```sh
python scripts/demo_tecnica.py \
  --evidencia results/demo_tecnica/ensayo_01/evidencia.json
```

También se puede ejecutar [01_demo_tecnica.ipynb](notebooks/01_demo_tecnica.ipynb) seleccionando el kernel de `.venv`. El notebook permite crear una corrida o leer evidencia existente; la preparación y la reproducción FIFO se ejecutan con los comandos de esta guía.

## Corridas de preparación y reproducción FIFO

Esta ruta mide ingesta y buffer; su salida es un archivo de sobres JSONL. La FIFO aún no está conectada al flujo HTTP de los servicios.

```sh
python scripts/data_pipeline.py prepare --source 10M.csv \
  --size 1000 --output data/prepared/ensayo_01_1K
python scripts/data_pipeline.py prepare --source 10M.csv \
  --size 10000 --output data/prepared/ensayo_01_10K
python scripts/data_pipeline.py replay \
  --events data/prepared/ensayo_01_1K/events.jsonl \
  --output results/fifo/ensayo_01/eventos.jsonl \
  --metrics results/fifo/ensayo_01/metricas.json --mode unlimited
```

Para analizar contrapresión con un consumidor lento:

```sh
python scripts/data_pipeline.py replay \
  --events data/prepared/ensayo_01_1K/events.jsonl \
  --output results/fifo/ensayo_02/eventos.jsonl \
  --metrics results/fifo/ensayo_02/metricas.json \
  --mode burst --capacity 8 --consumer-delay 0.001
```

`constant` limita la tasa; `burst` libera grupos en intervalos; `historical` acelera los intervalos del histórico; `unlimited` reproduce a la velocidad del consumidor. La configuración está en `configs/replay.json`; se cambia con `scripts/data_pipeline.py --config ruta.json ...`.

Las métricas incluyen conteos, throughput, latencia, espera del productor, ocupación máxima, bloqueos y memoria Python/proceso. La latencia empieza antes de encolar y termina al consumir; excluye el vaciado posterior del bloque a disco. El throughput incluye escritura y pacing, pero excluye la preparación. `event_time` conserva la fecha histórica; `ingested_at` registra la recepción real en UTC.

Para contrastar hashes, relaciones, conteos y preservación del orden FIFO:

```sh
python scripts/verify_pipeline.py \
  --prepared data/prepared/ensayo_01_1K data/prepared/ensayo_01_10K \
  --metrics results/fifo/ensayo_01/metricas.json results/fifo/ensayo_02/metricas.json \
  --output results/fifo/verificacion_01.json
```

Con la configuración predeterminada `configs/replay.json`, cada preparación de tamaño N contiene N−13 filas del prefijo original y 13 eventos reservados. `--all-source` conserva todas las filas originales y añade esos 13 eventos. `--size` admite enteros y sufijos como `100K`, `1M` y `10M`. `prepare --format parquet` y `replay --events archivo.parquet` admiten Parquet. Los prefijos pueden cortar sesiones y órdenes; esta limitación se registra en el manifiesto.

### Generación sintética configurable por tamaño

`configs/prepare.json` define parámetros comunes y perfiles `1K`, `10K`, `100K`, `1M` y `10M`. Cada perfil puede sobrescribir parámetros, incluyendo campos individuales de `synthetic`; los demás se heredan. Por ejemplo:

```sh
python scripts/data_pipeline.py --config configs/prepare.json prepare \
  --profile 1K --source 10M.csv --output data/prepared/perfil_1K
python scripts/data_pipeline.py --config configs/prepare.json prepare \
  --profile 1M --source 10M.csv --output data/prepared/perfil_1M
```

También se puede indicar `--size 100K` en lugar de `--profile`. Ambos son excluyentes. Cada salida debe ser nueva. El formato de estos perfiles es Parquet; `--format jsonl` lo sobrescribe.

Hay un script de ejemplo para cada escala. Ejecutar el que corresponda desde la raíz del proyecto:

```sh
bash scripts/ejemplos/generar_1K.sh
bash scripts/ejemplos/generar_10K.sh
bash scripts/ejemplos/generar_100K.sh
bash scripts/ejemplos/generar_1M.sh
bash scripts/ejemplos/generar_10M.sh
```

Cada script usa `configs/prepare.json`, la fuente `10M.csv` y la salida `data/prepared/perfil_<escala>/`, donde se generan los archivos Parquet, `entities.sqlite` y `manifest.json`. Usa `.venv/bin/python` cuando está disponible y, en caso contrario, `python3`. Las rutas predeterminadas se resuelven respecto al proyecto, por lo que también se puede invocar el script por su ruta absoluta desde otro directorio.

Para cambiar fuente, salida o formato, pasar opciones al script. Para cambiar configuración o intérprete, usar `CONFIG` o `PYTHON_BIN`. Las rutas personalizadas relativas se interpretan desde el directorio donde se ejecuta el comando:

```sh
bash scripts/ejemplos/generar_1K.sh \
  --source /ruta/datos.csv --output data/prepared/ensayo_02_1K
CONFIG=configs/prepare.json PYTHON_BIN=.venv/bin/python \
  bash scripts/ejemplos/generar_100K.sh --output data/prepared/ensayo_02_100K
```

Si la carpeta de salida ya existe, elegir otra con `--output`; los scripts no sobrescriben preparaciones anteriores. `--help` muestra las opciones de preparación.

**N es el total exacto de registros de eventos**, incluyendo reenvíos. Con `synthetic.fraction: 0.20`, los presupuestos son:

| Perfil | Total | Originales del CSV | Sintéticos |
|---|---:|---:|---:|
| 1K | 1.000 | 800 | 200 |
| 10K | 10.000 | 8.000 | 2.000 |
| 100K | 100.000 | 80.000 | 20.000 |
| 1M | 1.000.000 | 800.000 | 200.000 |
| 10M | 10.000.000 | 8.000.000 | 2.000.000 |

La configuración es experimental; las probabilidades no están estimadas del histórico. Para personalizar un perfil se puede escribir, por ejemplo, `"100K": {"size": 100000, "synthetic": {"fraction": 0.30, "p_return": 0.12}}`.

| Parámetro | Efecto |
|---|---|
| `seed` | Misma fuente, código, configuración y semilla reproducen los eventos. Cambiarla genera otra realización. |
| `synthetic.fraction` | Fracción de N que será sintética, entre 0 y 1. Se redondea al entero más cercano, con mitades hacia arriba. |
| `synthetic.include_controlled` | Incluye los 13 eventos controlados dentro del presupuesto sintético. |
| `synthetic.scenario_weights` | Pesos de elección de sesiones de compra, navegación y ráfagas de pagos fallidos; no son porcentajes exactos de eventos. |
| `synthetic.basket_size` | Rango de productos por orden, limitado por el catálogo disponible; máximo configurable de 100. |
| `synthetic.p_return`, `synthetic.p_review` | Probabilidades por compra de generar devolución y reseña. |
| `synthetic.resend_fraction` | Reenvíos dinámicos como fracción del presupuesto sintético. Incluidos en N y adicionales al reenvío del escenario controlado. |
| `synthetic.users_per_event` | Tamaño del conjunto de usuarios: esta proporción de los eventos dinámicos originales, truncada y con mínimo uno. Las identidades se calculan bajo demanda. |
| `synthetic.n_flagged` | Cantidad de entidades señaladas de cada clase: cuenta, dispositivo y método de pago. |
| `synthetic.catalog_limit` | Máximo de productos cargados en memoria para la generación; selección estable por `product_id`. El catálogo persistido conserva todos los productos observados. |
| `synthetic.catalog_source_rows` | Filas del CSV usadas solo para obtener catálogo y rango temporal cuando `fraction` es 1. |
| `chunk_size` | Tamaño de los bloques de exportación y umbral de commits; en generación los commits se hacen al terminar una sesión. |

Con `fraction: 1.0`, todos los eventos son sintéticos, pero se sigue necesitando el CSV para obtener atributos del catálogo y fechas. Con `fraction: 0`, se debe desactivar `include_controlled`. Se rechazan presupuestos que no alcancen para los escenarios controlados y los reenvíos. El modo por fracción requiere un tamaño: no admite `--all-source` ni `sample`. La configuración por cantidades de órdenes de `configs/sample.json` conserva su uso con `sample`; su generación también es incremental.

El generador mantiene una sesión en memoria. Antes de aceptar una sesión comprueba que cabe en el presupuesto; si no cabe, revierte sus órdenes pendientes y completa el resto con una sesión corta de navegación. Esta corrección del último tramo se registra como `tail_events`. Los candidatos a reenvío se guardan en una tabla auxiliar SQLite que contiene referencias a eventos; cada reenvío recupera un solo payload. En perfiles se elige con reemplazo, por lo que un original puede reenviarse varias veces. En la configuración histórica por cantidades se elige sin reemplazo. La tabla auxiliar se elimina al terminar.

Parquet se exporta por bloques y SQLite ordena globalmente por fecha usando almacenamiento temporal en disco. La memoria depende del catálogo limitado, la sesión y el bloque; el espacio en disco crece con N y contiene tanto SQLite como los archivos exportados. Las escalas son corridas independientes y no se garantiza que una sea prefijo de otra.

Cada `manifest.json` conserva `profile`, `config` efectiva, `generator_version`, `selection.budget`, `selection.synthetic_summary`, conteos por origen/tipo, hashes y validaciones. `synthetic_summary` describe los eventos dinámicos; `counts` incluye también los originales y los controlados. `validation.exact_size` comprueba N y `validation.origin_budget_matched` comprueba la proporción resuelta. Los conteos reflejan lo escrito, no valores editables del manifiesto. El esquema de eventos sigue siendo `1.0`; la versión de generación es `streaming-v2`.

## API y tráfico HTTP

Iniciar la API con los datos preparados:

```sh
ECOMMERCE_DATOS=data/prepared_5K PRECARGAR=0 \
  python -m uvicorn API_SERVICIOS.main:app --host 127.0.0.1 --port 8000
```

La documentación interactiva está en <http://127.0.0.1:8000/docs>. El arranque carga catálogo, inventario y señalados; `PRECARGAR=1` reproduce además los eventos al iniciar. El resto del estado se construye con el tráfico recibido.

En otra terminal, desde la raíz y con el entorno activado:

```sh
python -m API_SERVICIOS.cliente_trafico \
  --lote 250 --reenvios 0.02 --invalidos 0.01 --semilla 2026
```

El cliente admite `--url` y `--eventos` para otro servidor o archivo. Para verificar el flujo HTTP, reiniciar primero la API con `PRECARGAR=0` y ejecutar el siguiente comando sobre ese estado vacío, sin lanzar antes el cliente:

```sh
python scripts/verificar_api_funcional.py \
  --datos data/prepared_5K --salida results/api_funcional_01.json
```

El verificador genera su propio tráfico y contrasta conteos, ventas, devoluciones, stock, idempotencia, co-compra y atención de la cola. Modifica el estado de la API: reiniciarla antes de repetir. No enviar el cliente ni el verificador sobre una instancia precargada si se quiere contrastar una sola reproducción.

## Pruebas y estado de validación

```sh
python -m unittest discover -s tests -v
```

La suite cubre estructuras, muestreo/Parquet, reproducción, API y evidencia del análisis.

La integración FIFO → API, el B+Tree persistente en disco, Label Propagation, las mediciones de escala 100K–10M y la campaña de repeticiones independientes siguen pendientes. El estado de la API vive en memoria en un único proceso y se serializa mediante `RLock`. El grafo refleja compras aceptadas en ingesta, incluidas órdenes que podrían retenerse al atenderlas; las devoluciones no deshacen sus aristas. Los escenarios de actividad sospechosa no acreditan eficacia contra fraude real.

## Servicios y decisiones del dominio

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


### Decisiones y límites

- **Idempotencia.** Un reenvío (mismo `event_id` y contenido) no vuelve a contar compras, stock ni aristas. Si el `event_id` coincide pero el contenido es distinto, el evento se rechaza. La etiqueta `is_injected_duplicate` nunca se consulta.
- **Prioridad.** Sigue la regla explícita de `POLICIES['priority']`: pago fallido = 100, express = 10 y el resto 0. Se recalcula en la ingesta y no confía en el valor que manda el cliente.
- **Fraude.** Un positivo del Bloom solo cuenta tras verificarlo en el registro exacto. Si el CMS supera el umbral (5 intentos en 600 s), se confirma con el conteo exacto antes de bloquear. Las órdenes bloqueadas quedan retenidas al atenderlas. Las etiquetas de anomalía sirven solo para evaluar la simulación.
- **Stock.** Es sintético: `supplied` del inventario preparado más `stock_base` (10), al que el tráfico resta compras y suma devoluciones.
- **Índices.** KD-Tree, HNSW y LSH se reconstruyen en diferido (si hubo cambios y pasaron 30 s) o con `/admin/reconstruir`. PageRank y Louvain se recalculan solo si cambió el grafo.
- **Concurrencia.** El estado vive en memoria, en un solo proceso, y un `RLock` serializa las operaciones. El B+Tree también es en memoria; la versión en disco y las mediciones de escala quedan para los benchmarks.

## Guion de exposición en Swagger `/docs`

La documentación interactiva está en `http://127.0.0.1:8000/docs`. El notebook ya deja visibles consultas, respuestas resumidas y figuras; no hace falta ejecutar todos los métodos durante los cuatro minutos.

### Escena 1: prioridades y fraude — 60 segundos

Iniciar una API sin eventos precargados; el catálogo puede estar cargado:

```sh
PRECARGAR=0 .venv/bin/python -m uvicorn API_SERVICIOS.main:app
```

1. En `/salud`, verificar `eventos_aceptados=0`. Reiniciar si hay tráfico previo.
2. En `POST /eventos/lote`, pegar el contenido de `escenario_prioridades.json` de una corrida generada. Son cuatro eventos sintéticos enviados desordenados.
3. Consultar `GET /ordenes/cola`: deben aparecer `demo:alerta`, `demo:express`, `demo:estandar` y `demo:programada`, en ese orden.
4. Ejecutar `POST /ordenes/atender?n=4`: la alerta queda revisada; las órdenes, despachadas. El heap usa clase, plazo y llegada, no una jerarquía fija de tipos de entrega.
5. En `POST /fraude/senalados`, registrar `tipo=account`, `valor=demo:senalado`.
6. En `POST /fraude/verificar`, enviar `{"user_id":"demo:senalado"}` y luego `{"user_id":"demo:limpio"}`. El primero se bloquea por señal confirmada; el segundo se permite.
7. Mostrar la figura `02_cms`: en seis intentos cercanos, la estimación se contrasta con conteo exacto y alcanza el umbral de cinco.

Un positivo de Bloom significa «posiblemente señalado». La demo consulta también 10.000 identificadores realmente ausentes y registra FPR y falsos negativos. Si no hay falsos positivos, se muestra cero observado; no se inventa uno. La FPR de este escenario pequeño no caracteriza todo el tráfico. El escenario CMS evita bordes de ventana; su coincidencia no demuestra que el CMS sea siempre exacto.

### Escenas 2–4: similitud, grafo y servicio — 150 segundos

Detener la API anterior y reiniciarla con precarga. Así los eventos sintéticos anteriores no contaminan el grafo:

```sh
PRECARGAR=1 ECOMMERCE_DATOS=data/prepared_5K .venv/bin/python -m uvicorn API_SERVICIOS.main:app
```

Usar los identificadores y el término elegidos automáticamente en `evidencia.json → servicio` o en la celda «Servicio al usuario» del notebook. No enviar además el cliente de tráfico sobre la precarga.

| Tiempo | Consulta en `/docs` | Qué explicar / figura de apoyo |
|---|---|---|
| 50 s | `POST /admin/reconstruir`; `GET /productos/{id}/similares?metodo=knn&k=5` y después `metodo=hnsw` | Mismo producto, representación y métrica. Coincidencias y recall; figura `03_similitud_vectorial`. |
| 20 s | La misma ruta con `metodo=minhash` | Similitud por usuarios, distinta de similitud de atributos; figura `04_similitud_conjuntos`. |
| 45 s | `/admin/estadisticas`, `/cocompra/pares`, `/cocompra/influyentes`, `/cocompra/comunidades?min_tamano=1` | V/E efectivos, peso por órdenes, comunidades y PageRank frente a grado. Figura `08_subgrafo`. |
| 35 s | `/buscar/autocompletar`, `/buscar`, `/productos/{id}/complementarios`, `/usuarios/{id}/recomendaciones`, `/panel` | El usuario recibe búsqueda y recomendaciones; el operador observa ventas, alertas y cola. |

El endpoint HNSW calcula también KD-Tree para mostrar recall. **No usar su tiempo HTTP como tiempo de HNSW puro.** El notebook mide directamente cada búsqueda, fuera del transporte, enriquecimiento y cálculo de calidad.


## Qué ejecuta y cómo leer los resultados

| Bloque | Datos y referencias | Evidencia |
|---|---|---|
| Prioridad | Escenario sintético aislado; atención contrastada con orden esperado | `prioridades.csv`, solicitudes/respuestas en `control.consultas` |
| Bloom y CMS | Pertenencia exacta; frecuencias exactas del mismo escenario | `bloom.csv`, `bloom_calidad.csv`, `cms.csv` |
| KD-Tree / HNSW | Vectores actuales de 19 dimensiones; referencia por fuerza bruta sobre todos los productos elegibles | `similitud_mediciones.csv`, `similitud_resumen.csv`, `vecinos.csv` |
| MinHash + LSH | Conjuntos de usuarios con interacción positiva; Jaccard exhaustivo sobre todos los conjuntos elegibles | `vecinos_conjuntos.csv`, `similitud_mediciones.csv` |
| Grafo | Compras aceptadas; un par por orden distinta; verificación exhaustiva del conjunto de aristas y sus pesos | `grafo_resumen.csv`, `nodos.csv`, `aristas.csv`, `comunidades.csv` |
| Usuario | Búsqueda, rangos de precio, complementarios y recomendaciones híbridas | `busqueda.csv`, `rango_precios.csv`, `complementarios.csv`, `recomendaciones.csv` |

La consulta de fuerza bruta vectorial incluye distancias y ordenación completa para seleccionar K; es una referencia simple. En MinHash se comparan búsqueda LSH pura y Jaccard exhaustivo; la generación de firmas queda fuera. Se aplica un calentamiento por consulta y método, y se alterna su orden con semilla fija. Las repeticiones ocurren sobre **índices fijos**. Las tablas informan media, desviación muestral, mediana, p95, observaciones y consultas distintas; no equivalen a construcciones independientes.

La calidad vectorial conserva recall por IDs y recall que acepta empates en la distancia de corte. Primero se verifica KD-Tree contra fuerza bruta. Para conjuntos se aceptan empates de Jaccard; revisar `referencia_positiva` para distinguir consultas cuyo mejor vecino tiene similitud cero. No interpretar un recall alto sobre empates cero como evidencia de buenas recomendaciones.

## Criterio del grafo acordado

**La carga se expresa en eventos; el tamaño del grafo es un resultado.** Por ejemplo, 10M eventos no obligan a tener 10M productos. No se añaden productos sintéticos para igualar ambas cantidades.

Registrar por corrida:

- V total: productos comprados incorporados al grafo, incluidos aislados.
- V analizado: productos con al menos una relación; es la población que usa el servicio para PageRank y Louvain.
- E: pares distintos, contados una sola vez; cada arista se almacena en ambas listas de adyacencia.
- Peso: número de órdenes distintas compartidas. Repetir un par en otra orden aumenta su peso, sin aumentar E.
- Componentes, aislados, grado medio no ponderado `2E/V`, grado ponderado, modularidad, comunidades y hash de la instantánea.

Los algoritmos de la demo se ejecutan sobre todos los nodos con co-compra. Solo la **visualización** selecciona hasta 30 productos por PageRank; el título indica el tamaño mostrado y sus métricas no sustituyen a las globales. El archivo completo de nodos y aristas queda exportado. Los puntos de la curva de crecimiento son instantáneas acumulativas del mismo archivo, no cinco experimentos independientes.

La implementación registra compras aceptadas por ingesta; una orden bloqueada se retiene posteriormente al atenderla. El grafo no representa exclusivamente despachos aprobados y las devoluciones no eliminan sus relaciones. Esta semántica debe acompañar las conclusiones comerciales.

Queda por confirmar con el docente si los grafos resultantes de las cinco escalas de eventos cubren el requisito académico o si también solicita grafos sintéticos de tamaño controlado. La demo no presupone esa aprobación.

## Incorporar evidencia al informe final

Cada corrida produce:

```text
results/demo_tecnica/<corrida>/
  evidencia.json                 # consultas, respuestas, parámetros, hashes y mediciones crudas
  escenario_prioridades.json    # payload listo para pegar en /docs
  resumen.md                    # resultados y límites con enlaces a figuras
  tablas/*.csv                  # datos para análisis y edición
  tablas/*.md                   # tablas listas para copiar
  figuras/*.png                 # imágenes para documentos y diapositivas
  figuras/*.svg                 # vector editable
  figuras/*.pdf                 # vector para LaTeX
  figuras/pies.md               # pies de figura reutilizables
```

`metadata` conserva Python, plataforma, versiones de dependencias, configuración, semilla, revisión Git y hashes de entradas/código. El estado de trabajo puede contener cambios sin commit; los hashes permiten identificar el contenido ejecutado. Para repetir la selección con el mismo orden de hashing, iniciar Python con `PYTHONHASHSEED=2026`; cambiarlo después de iniciar el kernel no tiene efecto.

Se puede regenerar la presentación de resultados sin volver a medir:

```sh
.venv/bin/python scripts/demo_tecnica.py --evidencia results/demo_tecnica/ensayo_01/evidencia.json
```

El notebook ofrece además modo de lectura de JSON guardado. Para convertir un notebook con salidas a HTML:

```sh
.venv/bin/python -m nbconvert --to html notebooks/01_demo_tecnica.ipynb --output-dir results/demo_tecnica
```

## Límites de esta entrega

La demo no sustituye los experimentos de escalabilidad, memoria actual/pico, 100 repeticiones cuando sean viables, error del CMS bajo distribuciones variadas ni estabilidad de comunidades. PageRank y Louvain tienen una medición piloto cada uno, sin desviación estimable. Label Propagation permanece pendiente; no se presenta una comparación de comunidades inexistente. Los tiempos HTTP del notebook corresponden a ASGI local, no a una red ni a un ensayo de concurrencia.

La ruta HTTP no atraviesa la FIFO de pipeline de ingesta. Su conexión con la API sigue siendo un trabajo distinto; esta demo muestra los servicios implementados y sus salidas, sin afirmar que certifica por sí sola las diez etapas conectadas.
