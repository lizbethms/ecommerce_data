# Plan del proyecto de Estructuras de Datos y Algoritmos

## Objetivo y alcance

Implementar la opción B del enunciado: un sistema de comercio electrónico que procese un stream de navegación, compras y eventos operativos. Cada etapa debe consumir una salida real de otra etapa y contribuir a una recomendación, alerta, ranking o resultado Top-K observable.

La solución combinará el histórico real de REES46 con información derivada y escenarios sintéticos reproducibles. El proyecto cubrirá:

- Procesamiento con prioridades.
- Búsquedas rápidas, índices de disco y almacenamiento eficiente.
- Filtrado probabilístico y estimación de frecuencias por ventana temporal.
- Similitud de conjuntos y búsqueda aproximada de vecinos.
- Co-compra, influencia y comunidades de productos.
- Servicio al usuario y medición del pipeline completo.

Este documento combina el diseño previsto con el estado verificado de las etapas 0 y 6. La etapa 6 cuenta con API `/fraude`, servicio, persistencia CSV y pruebas 1K/10K, descritos abajo. Las etapas 1–5 y 7–9 y la integración completa permanecen pendientes.

## Data

### Fuente y validación inicial

Archivo local: `10M.csv`. Columnas de origen:

```text
event_time,event_type,product_id,category_id,category_code,brand,price,user_id,user_session
```

La inspección completa del archivo produjo estos resultados:

| Característica | Resultado |
|---|---:|
| Registros | 10.000.000 |
| Vistas (`view`) | 9.627.820 |
| Carritos (`cart`) | 199.354 |
| Compras (`purchase`) | 172.826 |
| Periodo | 2019-10-01 00:00:00 a 2019-10-08 17:26:09 UTC |
| `category_code` vacío | 3.224.119 |
| `brand` vacío | 1.387.109 |
| `user_session` vacío | 1 |
| Precios iguales a cero | 15.522 |
| Precios negativos o no convertibles a número | 0 |
| Retrocesos de fecha entre filas consecutivas | 0 |
| Grupos usuario–sesión con compras | 145.986 |
| Grupos usuario–sesión con compras de al menos dos productos distintos | 11.502 |

Esta revisión no demuestra ausencia de duplicados ni valida todas las relaciones entre entidades. Esas comprobaciones deberán incorporarse al proceso de preparación.

### Adecuación al escenario

El enunciado recomienda REES46 como fuente para ecommerce y permite generar el componente sintético del stream. El histórico sirve para navegación, preferencias, popularidad e interacciones usuario–producto, pero tiene estas brechas:

| Necesidad | Información disponible | Adecuación prevista |
|---|---|---|
| Órdenes y prioridad de entrega | Compras, sin orden ni modalidad de entrega | Generar órdenes y modalidades express, estándar y programada. |
| Co-compra dentro de la misma orden | Usuario y sesión | Crear relaciones de orden sintéticas; una sesión no acredita una orden real. |
| Alertas de pago y actividad sospechosa | Usuario, fecha y tipo de evento | Generar intentos de pago, dispositivos, medios de pago simulados y etiquetas de los casos inyectados. |
| Disponibilidad | Sin inventario | Crear inventario sintético consistente con las compras y devoluciones simuladas. |
| Búsquedas y autocompletado | Categorías y marcas, con valores faltantes | Generar consultas y nombres sintéticos de producto; permitir sugerencias de categorías y marcas disponibles. |
| Devoluciones y reseñas | No existen esos eventos en el archivo | Generarlos con referencias coherentes a compras y productos. |
| Vectores para KNN y ANN | Precio, categorías y comportamiento | Construir características numéricas; los identificadores no son coordenadas de similitud. |

### Esquema enriquecido y trazabilidad

Un registro completo será un evento válido según su tipo. Los campos que no apliquen podrán quedar nulos: una vista no necesita una orden ni un medio de pago.

| Grupo | Campos previstos | Regla |
|---|---|---|
| Identidad | `event_id`, `schema_version` | Identificador estable; un reenvío duplicado conserva el mismo `event_id`. |
| Tiempo | `event_time`, `ingested_at` | Fecha del dominio en UTC y fecha de recepción; conservar la fecha histórica original. |
| Procedencia | `event_origin`, `source_row_id`, `generation_run_id`, `synthetic_fields` | Distinguir eventos reales/sintéticos y campos añadidos a eventos reales. Guardar semilla y configuración en el manifiesto de generación. |
| Interacción | `event_type`, `user_id`, `user_session`, `product_id` | Validar según el tipo; conservar identificadores originales y separar el espacio de identificadores sintéticos. |
| Producto | `category_id`, `category_code`, `brand`, `price` | Separar valores observados de atributos completados o derivados. |
| Orden | `order_id`, `quantity`, `delivery_type`, `scheduled_at` | Obligatorios cuando correspondan; una orden puede contener varios productos. |
| Prioridad | `priority`, `priority_reason` | Derivadas de reglas explícitas de urgencia y alerta, sin utilizar etiquetas de evaluación. |
| Pago | `payment_attempt_id`, `payment_method_id`, `device_id`, `payment_status` | Identificadores ficticios; obligatorios según el evento de pago. |
| Eventos complementarios | `query`, `rating`, `original_purchase_event_id` | Consulta para búsquedas, puntuación para reseñas y referencia de compra para devoluciones. |
| Evaluación | `scenario_id`, `is_injected_duplicate`, `is_injected_anomaly` | Metadatos para verificar escenarios; no usarlos como señales de detección. |

El catálogo, el inventario, las órdenes y los vectores se mantendrán también como entidades separadas, evitando repetir atributos grandes en cada evento.

### Reglas de consistencia y calidad

1. Preservar el archivo original y generar los datos preparados en otra ubicación.
2. Normalizar fechas a UTC; tratar IDs como identificadores y usar una representación monetaria que evite errores de redondeo.
3. Conservar `category_id` cuando falte `category_code`. Para marcas o códigos desconocidos, usar un valor explícito o completar desde observaciones consistentes del producto, registrando la procedencia.
4. Marcar precios cero para revisión; no eliminarlos ni reemplazarlos automáticamente sin una regla documentada.
5. Tratar la sesión ausente con una regla explícita y trazable, sin asociarla arbitrariamente a otra sesión.
6. Asignar identidad estable antes de inyectar duplicados. La igualdad de todas las columnas originales será una señal de posible duplicado, no una prueba de que dos acciones legítimas sean la misma.
7. Para compras reales sin orden, construir agrupaciones sintéticas documentadas, por ejemplo por usuario, sesión y ventana temporal. No presentar esas agrupaciones como órdenes observadas. Generar además órdenes controladas de varios productos para probar co-compra.
8. Mantener relaciones temporales coherentes: pagos, compras y devoluciones deben respetar el ciclo simulado. Una devolución no puede superar la cantidad comprada ni preceder a la compra.
9. Establecer una política reproducible para cambios de precio, conflictos de catálogo e inventario. El precio observado en un evento no demuestra el precio actual de un producto.
10. Guardar configuración, semilla, conteos por tipo, proporciones sintéticas y resultados de validación. Las etiquetas de anomalía solo permiten evaluar escenarios simulados; no prueban eficacia contra fraude real.

## Generación de datasets y simulador

### Estrategia de generación

Conservar los 10 millones de eventos de origen. El enriquecimiento y la incorporación de nuevos tipos podrán producir un conjunto maestro mayor de 10 millones. De este se construirán versiones experimentales de **1K, 10K, 100K, 1M y 10M eventos** con selección reproducible y orden temporal.

Los subconjuntos deberán preservar o resolver sus dependencias de órdenes, pagos y devoluciones. Se documentarán los límites que corten sesiones u órdenes. El generador debe reservar escenarios controlados suficientes para demostrar prioridades, alertas y co-compra, sin depender de que aparezcan por azar en una muestra pequeña.

No se reemplazarán eventos reales silenciosamente para alcanzar un conteo. Cada versión tendrá un manifiesto con su composición y reglas de selección. Para medir tráfico representativo y casos de estrés se usarán configuraciones diferenciadas y documentadas.

### Motor de reproducción

Se usará **Python + `asyncio`** para la ingesta y coordinación de la etapa 0. SimPy sería una alternativa para modelar recursos y tiempos de espera con un reloj de simulación, pero no es necesario para el alcance inicial.

```text
REES46, lectura por bloques
          ↓
Validación y enriquecimiento reproducible
          ↓
Eventos reales + escenarios sintéticos + manifiesto
          ↓
Reproductor: velocidad, ráfagas y tiempo histórico
          ↓
Cola FIFO acotada → etapas 1 a 9
```

El simulador deberá:

- Leer por bloques sin cargar todos los registros en memoria.
- Reproducir tráfico constante, ráfagas e intervalos históricos acelerados, conservando el tiempo del evento.
- Inyectar reenvíos, órdenes de distintas prioridades e intentos de pago anómalos con semilla fija.
- Limitar colas y aplicar contrapresión cuando los consumidores sean más lentos.
- Separar la coordinación asíncrona del trabajo intensivo de CPU; `asyncio` no paraleliza por sí solo los cálculos de similitud o grafo.

## Arquitectura del pipeline

Las diez etapas serán parte de una ejecución integrada. Las elecciones siguientes son el diseño inicial; deberán justificarse mediante las comparaciones del proyecto.

| Etapa | Nombre / bloque | Estructura o algoritmo | Función y salida consumible |
|---|---|---|---|
| 0 | Ingesta y buffer / S1 | FIFO acotada | Recibir eventos y emitirlos hacia el preprocesamiento. |
| 1 | Preprocesamiento por lotes / S2 | Ordenación y búsqueda binaria | Validar, normalizar y detectar duplicados del lote; emitir eventos válidos y decisiones de calidad. |
| 2 | Cola con prioridades / S3 | Heap | Ordenar por urgencia de pago/alerta y modalidad de entrega; desempatar de forma estable y controlar inanición. |
| 3 | Almacenamiento, lookup y caché / S4 | Hash table, matriz dispersa y LRU | Recuperar producto/usuario y preparar actualizaciones de interacciones. |
| 4 | Indexación principal / S5 | B+Tree en disco | Mantener índices por claves, fecha o precio y resolver consultas puntuales y por rango. |
| 5 | Índice multidimensional / S6 | KD-Tree y KNN exacto | Consultar características numéricas de baja dimensión y producir candidatos exactos de referencia. |
| 6 [FIJA] | Filtrado probabilístico / S7 | Bloom Filter y Count-Min Sketch | Consultar pertenencia y estimar intensidad por clave y ventana; emitir señales y verificaciones exactas cuando proceda. |
| 7 [FIJA] | Similitud aproximada / S7 | MinHash + LSH y HNSW | Obtener candidatos por conjuntos y vectores; emitir productos relacionados y métricas frente a métodos exactos. |
| 8 [FIJA] | Grafo del dominio / S8–S9 | Personalized PageRank y Louvain | Actualizar co-compra por orden confirmada, con procedencia sintética documentada; producir complementos y comunidades. |
| 9 | Servicio y visualización / transversal | Top-K y Trie | Combinar candidatos, popularidad y señales del grafo para recomendaciones, búsquedas, autocompletado y paneles. |

### Integración y estado

Cada evento circulará en un sobre con `event_id`, referencias a entidades, resultados de etapas y tiempos de procesamiento. La salida de cada etapa será entrada de la siguiente; un evento puede aportar contexto o consultar un índice aunque no actualice todas las estructuras.

Las etapas 3–5 prepararán cambios o consultarán estado confirmado. Las decisiones de la etapa 6 determinarán qué actualizaciones se confirman y alimentan los índices, las recomendaciones y el grafo. Esto requiere un mecanismo explícito de confirmación o actualizaciones idempotentes para no contabilizar dos veces un reenvío.

Un evento rechazado por validación o identificado como duplicado conservará una salida observable de rechazo o descarte. Para la demostración se elegirá además un evento válido que atraviese las diez etapas hasta el servicio.

### Representaciones para similitud y grafo

- **Matriz usuario–producto:** interacciones ponderadas por tipo, con pesos configurables. Analizar cómo la mayor cantidad de vistas afecta las señales de compra.
- **Conjuntos para MinHash:** atributos de cada producto con prefijos de campo, por ejemplo `{categoria:running, marca:X, uso:deporte}`; comparar Jaccard estimado con Jaccard exacto. Excluir identificadores únicos y valores desconocidos compartidos que inflarían artificialmente la similitud. Como extensión separada, evaluar conjuntos de usuarios que interactuaron con cada producto dentro de una ventana; no mezclar ambas representaciones en un mismo experimento.
- **Vectores para HNSW:** características de producto derivadas de atributos y comportamiento. Ajustar transformaciones con el periodo de referencia, sin incorporar información futura de evaluación.
- **KNN:** usar el mismo espacio y métrica al comparar HNSW con búsqueda exacta. El KD-Tree podrá usar una representación de baja dimensión; si difiere de la de HNSW, reportarlo como experimento separado y usar fuerza bruta en el espacio de HNSW.
- **Grafo de co-compra:** productos como nodos y aristas no dirigidas ponderadas por el número de órdenes distintas compartidas. Contabilizar cada par una vez por orden, sin bucles ni doble conteo por reenvíos. Definir la finalización de órdenes y la ventana temporal.
- **Frecuencias:** definir clave, ventana, umbral y política de expiración para CMS; por ejemplo, intentos de pago por usuario en una ventana. Un CMS simple no elimina por sí mismo eventos vencidos: usar ventanas por bloques o rotación documentada.
- **Pertenencia:** un positivo del Bloom Filter no prueba identidad ni fraude. Verificar con un registro exacto antes de descartar una operación legítima o bloquear una cuenta.

## Diseño implementable de las etapas obligatorias 6–8

Las tres etapas deben resolver funciones del ecommerce y entregar resultados consumidos por el servicio. La etapa 6 requiere **Bloom Filter y Count-Min Sketch**; la etapa 7 requiere **una técnica de conjuntos y una técnica ANN**, por lo que se implementarán MinHash + LSH **y** HNSW. La etapa 8 requiere **ranking y comunidades**, resueltos con Personalized PageRank y Louvain. Ninguna de estas elecciones reemplaza las otras siete etapas del pipeline.

### Relación con los requerimientos del ecommerce

| Requerimiento funcional | Algoritmos y responsabilidad | Salida observable |
|---|---|---|
| Posible fraude: reconocer entidades señaladas | Bloom Filter como prefiltro y tabla hash como verificación exacta | Coincidencia verificada o falso positivo registrado. |
| Posible fraude: intensidad de intentos | CMS por ventana y verificador exacto de candidatos | Alerta con clave, ventana, estimación y conteo verificado. |
| Productos relacionados: alternativas similares | MinHash + LSH sobre atributos y HNSW sobre vectores | Top-K de productos similares y comparación con referencias exactas. |
| Co-compra y cross-selling: complementos | Grafo ponderado y Personalized PageRank desde producto/carrito | Top-K de complementos con puntuación y contexto de consulta. |
| Agrupaciones de consumo | Louvain sobre el mismo grafo | Comunidad por producto, tamaños y métricas del grafo. |
| Servicio y panel | Consumo de las salidas anteriores en la etapa 9 | Productos similares, complementos, comunidades y alertas verificadas. |

### Etapa 6: pertenencia e intensidad de posibles intentos de fraude

**Bloom Filter.** Mantener un registro exacto de cuentas, dispositivos y medios de pago ficticios señalados. Construir el filtro con claves tipadas como `device:<id>`, `account:<id>` y `payment:<id>` para evitar colisiones semánticas entre entidades. Al recibir un intento de pago:

1. Consultar las claves aplicables en el filtro.
2. Si la respuesta es negativa, registrar que la clave no pertenece al conjunto insertado y continuar las demás validaciones; esto no acredita que el pago sea seguro.
3. Si la respuesta es positiva, consultar el registro exacto. Registrar por separado coincidencias verificadas y falsos positivos.
4. Emitir una señal de entidad señalada únicamente tras confirmación exacta; la política de negocio decidirá revisión, retención o bloqueo.

Configurar capacidad prevista y tasa objetivo de falsos positivos; registrar ocupación y claves insertadas para detectar saturación. El registro exacto será la fuente de verdad. Actualizar filtro y registro de forma consistente; reconstruir el Bloom Filter cuando se retiren entidades señaladas, pues el filtro estándar no admite borrado seguro.

**Count-Min Sketch.** La configuración inicial para la demo será:

| Parámetro | Decisión inicial |
|---|---|
| Evento contado | `payment_attempt`, una vez por `payment_attempt_id` válido. |
| Clave | `device_id`; cuentas y medios de pago serán extensiones configurables. |
| Reloj | `event_time` en UTC; la velocidad del reproductor no cambia la ventana. |
| Ventana | Cinco intervalos alineados de un minuto: el actual y los cuatro anteriores. |
| Expiración | Anillo de cinco CMS; reiniciar un bloque al reutilizarlo y expirar todos los vencidos ante saltos de tiempo. |
| Estimación | Sumar las estimaciones de la clave en los bloques activos. |
| Umbral de candidato | Estimación mayor o igual que 20 intentos; valor ilustrativo configurable, no calibrado para fraude real. |
| Confirmación | Conteo exacto por clave sobre los mismos intervalos antes de una acción restrictiva. |

Esta ventana tiene resolución de un minuto y no equivale exactamente a los últimos 300 segundos en cualquier instante. El comparador exacto deberá usar los mismos límites. El coordinador definirá un avance temporal monotónico y una política explícita para eventos tardíos; la prioridad del heap puede alterar el orden de llegada y no debe hacer retroceder ni reiniciar incorrectamente las ventanas.

Para el alcance académico, mantener un diccionario exacto de conteos por bloque con la misma expiración; servirá como verificador y referencia experimental. Reportar su costo junto al del CMS para no atribuir al sistema completo un ahorro que solo pertenece al sketch. Un CMS sin sobreflujo y con actualizaciones positivas puede sobreestimar por colisiones; no usar su estimación como evidencia suficiente para bloquear.

**Salida:** `risk_signals` con pertenencias consultadas, verificaciones, clave de frecuencia, límites de ventana, estimación, conteo exacto cuando aplique y decisión. Las etiquetas `is_injected_anomaly` quedan fuera del detector. La etapa 9 consumirá las alertas verificadas. Si se emite un nuevo evento de alerta hacia el heap, asignarle identidad y referencia al evento causal y evitar que vuelva a generar la misma alerta indefinidamente.

**Criterios de aceptación:** un positivo falso del Bloom Filter no bloquea una operación; una sobreestimación del CMS no genera una restricción sin confirmar; los reenvíos no incrementan dos veces el conteo; los intentos vencidos dejan de contribuir; la demo muestra estimación y conteo real.

### Implementación entregada de etapa 6: API `/fraude` y servicio

La etapa 6 funciona de forma independiente mediante FastAPI o procesamiento JSONL por lotes. Ambos adaptadores utilizan `FraudService`; las estructuras probabilísticas están separadas de transporte y persistencia. El adaptador por lotes admite eventos preparados y sobres reales de etapa 0, conserva los resultados anteriores y añade `stage_results["6"]` y `processing_times["6"]`. Esta entrega no implementa las etapas intermedias ni la confirmación de cambios de índices o grafo.

#### Contrato HTTP

| Método y endpoint | Contrato |
|---|---|
| `POST /fraude/eventos` | Entrada `{"evento": {...}}`; salida `evento_id`, `estado`, `senales_riesgo`. |
| `PUT /fraude/entidades/{tipo}/{identificador}` | Alta o actualización con `{"motivo":"Caso ficticio"}`. |
| `DELETE /fraude/entidades/{tipo}/{identificador}` | Retiro idempotente y reconstrucción del Bloom. |
| `GET /fraude/entidades` | Registro exacto de entidades señaladas. |
| `GET /fraude/metricas` | Configuración, contadores, ventana, capacidad y ocupación Bloom. |
| `GET /fraude/salud` | Disponibilidad y recuperación del historial. |

Los tipos de entidad son `cuenta`, `dispositivo` y `medio_pago`; internamente se mantienen claves `account:`, `device:` y `payment:`. Los nombres de campos del evento se conservan según `schema.py`. La API traduce la salida interna `risk_signals` al español. OpenAPI y ejemplos interactivos están en `/docs`.

Estados HTTP: `procesado`, `duplicado`, `no_aplica`, `fuera_de_ventana`. Las señales contienen pertenencias y verificación exacta, dispositivo contado, límites UTC inclusivo/exclusivo, estimación, conteo exacto para candidatos, motivos y decisión `continuar` o `revisar`. No hay bloqueo automático. HTTP 422 representa validación inválida, 409 identidad contradictoria y 503 fallo de persistencia.

#### Reglas implementadas

- Configuración en `configs/stage6.json`: Bloom con capacidad inicial 1.000 y tasa objetivo 1%; CMS epsilon 0,01 y delta 0,001; umbral 20. Hashes SHA-256 reproducibles y contadores sin desbordamiento de ancho fijo.
- Registro exacto como fuente de verdad. Los positivos Bloom se verifican; cambios del registro reconstruyen el filtro y su capacidad se amplía al excederla.
- Anillo de cinco minutos alineados UTC y verificadores exactos con igual expiración. El máximo `event_time` aceptado determina el reloj; los eventos tardíos dentro de la ventana cuentan, los anteriores quedan señalados sin incrementar frecuencias. Los eventos nuevos ajenos a pagos también avanzan el reloj.
- Deduplicación por `event_id` y `payment_attempt_id`, antes de actualizar ventanas. Los reenvíos equivalentes recuperan el resultado original; los cambios de contenido de negocio generan conflicto. Se excluyen metadatos de recepción, generación, calidad y evaluación del cotejo. Un reenvío conserva su decisión histórica aunque el registro cambie.
- Historial CSV con columnas `version,secuencia,operacion,contenido,sha256`. Contiene configuración inicial, cambios del registro y eventos válidos; confirma escrituras con `flush`/`fsync` antes de responder. La recuperación reproduce operaciones y rechaza corrupción o configuración incompatible indicando fila.
- Una instancia y un worker por historial, con bloqueo exclusivo de archivo y serialización de mutaciones. Una escritura fallida impide nuevas mutaciones hasta reiniciar e inspeccionar el historial. Las identidades se retienen para asegurar idempotencia; no hay compactación en esta versión.

#### Preparación, ejemplos y comandos

`prepare.py` incorpora el perfil opcional `stage6`; el predeterminado `stage0` conserva sus 13 escenarios. `schema.py` valida identificadores textuales y estados de pago. Cada dataset de etapa 6 reserva 39 registros sintéticos: los 13 originales y 24 pagos únicos del mismo dispositivo, un reenvío de pago y un pago después de expirar la ventana. Los manifiestos identifican perfil, composición y hashes, incluido `entidades.csv` con el registro inicial ficticio. SQLite sigue siendo un artefacto de preparación, no la persistencia del servicio.

Se generaron `data/prepared/fraude_1K` y `data/prepared/fraude_10K`, con exactamente 1.000 y 10.000 registros: 961/9.961 filas reales y 39 sintéticas. Los conjuntos previos de etapa 0 no se sobrescribieron.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
FRAUDE_HISTORIAL=data/fraude/demo_01.csv .venv/bin/uvicorn src.api.fraud:create_app --factory --workers 1 --host 127.0.0.1
# En otra terminal, con historial nuevo:
.venv/bin/python examples/fraude/probar_api.py
```

`examples/fraude/` incluye un CSV de entidades, pagos JSON normal/señalado/inválido/conflictivo, 28 eventos JSONL y sus resultados esperados. Son independientes del archivo original. Su README documenta curl, carga de entidades, lotes y reinicio.

```sh
# Generación; utilizar carpetas nuevas al repetir:
.venv/bin/python scripts/stage0.py prepare --profile stage6 --size 1000 --output data/prepared/fraude_1K
.venv/bin/python scripts/stage0.py prepare --profile stage6 --size 10000 --output data/prepared/fraude_10K
.venv/bin/python scripts/stage6.py --events examples/fraude/eventos.jsonl --entities examples/fraude/entidades.csv --history data/fraude/lote_01.csv --output results/lote_01.jsonl --metrics results/lote_01_metrics.json
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/verify_stage6.py
.venv/bin/python scripts/benchmark_stage6.py --output results/stage6_benchmark_metrics.json
```

#### Evidencia y límites de esta entrega

Pasaron 18 pruebas automatizadas, los 28 ejemplos contra HTTP real y las verificaciones completas de 1K/10K. Cada dataset produjo 30 pagos únicos contabilizados, dos reenvíos sin doble conteo y diez revisiones: cinco por entidad señalada y cinco por frecuencia. El pago final estimó 1 tras expirar los anteriores. Se comprobaron recuperación, hashes y reenvío después del reinicio.

Las corridas completas tardaron aproximadamente 0,114 s (1K) y 1,364 s (10K), incluyendo CSV y salida; no representan tiempos exclusivos de algoritmos. Los resultados están en `results/stage6_verification_metrics.json` y archivos por escala.

El benchmark de estructuras ejecutó 100 repeticiones en memoria por escala, separando construcción, actualización, consulta y medición de memoria. La tasa observada de falsos positivos Bloom fue 1,00%/0,82%, sin falsos negativos. El error medio CMS fue 0/3,753 y el máximo 0/27, sin subestimaciones. Las colisiones y sus verificaciones también se probaron mediante casos forzados.

El benchmark usa 1K/10K claves Bloom y 1K/10K actualizaciones de un CMS individual; no equivale a los 31 registros de pago de los datasets completos. El diccionario exacto ocupó menos memoria incremental que el CMS en estas entradas. El servicio añade cinco verificadores, deduplicación y persistencia; no se atribuye un ahorro global al sketch. Se documentan protocolo, complejidades y límites en [docs/etapa6.md](docs/etapa6.md), y métricas completas en `results/stage6_benchmark_metrics.json`. No se verificaron escalas mayores ni detección de fraude real.

### Etapa 7: productos similares por conjuntos y vectores

**MinHash + LSH.** Construir conjuntos de atributos desde el catálogo, generar firmas MinHash e indexarlas por bandas LSH. Ante una consulta por producto, recuperar candidatos y calcular Jaccard exacto sobre esos candidatos para ordenarlos. La referencia de evaluación calculará Jaccard por fuerza bruta sobre todo el catálogo elegible, no solo sobre lo recuperado por LSH. Excluir el producto consultado y definir una salida vacía o alternativa explícita cuando no existan atributos utilizables.

Guardar número de permutaciones, bandas, filas por banda, semilla y regla de selección de candidatos. Medir calidad tanto de la estimación de Jaccard como de la recuperación, pues reordenar exactamente los candidatos no recupera los productos omitidos por LSH.

**HNSW.** Construir vectores con precio transformado/normalizado, categorías y atributos codificados; las características de comportamiento se añadirán con una ventana histórica explícita. Persistir esquema, transformaciones, métrica y versión de los vectores. Los IDs de producto serán claves de recuperación, nunca coordenadas numéricas de similitud.

La búsqueda exacta de referencia recorrerá los mismos vectores con la misma métrica. Si el KD-Tree de la etapa 5 usa otras dimensiones, se evaluará aparte. Configurar y registrar `M`, `ef_construction` y `ef_search`; medir construcción, actualización, consulta, memoria y `recall@K`.

**Salida:** `similarity_candidates` con listas separadas para LSH y HNSW, `product_id`, puntuación/distancia, método y versión del índice. La etapa 9 combinará candidatos con una regla explícita, eliminará repetidos y productos sin disponibilidad, y producirá el Top-K. No sumar directamente Jaccard y distancias de escalas distintas; usar, por ejemplo, fusión por posiciones de ranking con parámetros documentados.

**Criterios de aceptación:** ambas técnicas se ejecutan en la demo; cada una se compara con su referencia exacta; no se recomienda el producto de entrada; los filtros de elegibilidad son iguales para el método aproximado y su referencia; se registra cómo cada lista contribuye al resultado final.

### Etapa 8: complementos y comunidades en el grafo de co-compra

**Construcción.** Mantener nodos de productos y aristas no dirigidas cuyo peso sea el número de órdenes confirmadas distintas que contienen ambos productos. Una orden con `m` productos distintos genera `m(m-1)/2` pares; varias unidades de un mismo producto no multiplican el peso. Agrupar por `order_id`, cerrar la orden con una señal explícita y registrar los IDs de órdenes ya aplicadas. Para compras históricas sin orden real, usar únicamente las agrupaciones sintéticas documentadas en la preparación.

Ejemplo verificable:

```text
Orden 101 confirmada: {laptop, mouse, funda}
Orden 102 confirmada: {laptop, mouse}
Resultado: peso(laptop, mouse)=2;
           peso(laptop, funda)=1; peso(mouse, funda)=1.
Reenviar la orden 101 conserva los mismos pesos.
```

No actualizar este grafo con vistas, carritos, pagos pendientes ni compras retenidas. La versión inicial representará co-compra histórica bruta: una devolución posterior se reportará por separado y no restará aristas; documentar esta semántica. Empezar con acumulación desde el inicio del replay; una ventana móvil del grafo será una extensión y requerirá retirar las contribuciones de órdenes vencidas.

**Personalized PageRank.** Personalizar desde el producto consultado o distribuir la masa inicial entre productos del carrito. Usar pesos de co-compra en las transiciones y excluir del resultado los productos semilla y los no disponibles. Parametrizar amortiguación, tolerancia y máximo de iteraciones. Para el panel de influencia global, ejecutar la misma familia con personalización uniforme. Comparar el ranking con grado ponderado, reportando el contexto global o personalizado de cada comparación.

**Louvain.** Ejecutar sobre una instantánea del mismo grafo ponderado para identificar comunidades de consumo. Comparar con Label Propagation, usando las mismas reglas de pesos y calculando modularidad bajo una convención común. Guardar semilla, resolución, tiempo, tamaños y estabilidad entre ejecuciones. Las comunidades describen asociaciones de compra, no categorías garantizadas ni relaciones causales.

Para no recalcular todo el grafo por evento, actualizar aristas al confirmar órdenes y programar ranking/comunidades por lotes o intervalos configurables. Cada salida indicará `graph_version` y fecha de corte; la demo esperará explícitamente el análisis de la versión que desea mostrar.

**Salida:** `graph_recommendations`, `global_influence` y `community_id` por producto, con versión del grafo. La etapa 9 mostrará complementos, influencia y agrupaciones, diferenciándolos de los productos similares de la etapa 7.

**Criterios de aceptación:** el ejemplo de dos órdenes produce los pesos esperados; los reenvíos no cambian el grafo; una compra pendiente no crea aristas; se muestran complementos desde una semilla, ranking global y comunidades; los métodos de comparación usan la misma instantánea.

### Contrato de integración y caso de demostración

El sobre del evento incorporará `risk_signals`, `similarity_candidates`, `graph_recommendations`, versiones de índices/grafo y tiempos por etapa. Las listas voluminosas podrán persistirse por referencia. Los nombres son contratos de diseño que deben concretarse en los módulos Python.

```text
Compra confirmada con order_id y payment_attempt_id referenciados
  → 0–1: recepción, validación, normalización y deduplicación
  → 2: prioridad de entrega/pago y desempate estable
  → 3–5: consulta de catálogo, índices y candidatos exactos
  → 6: consultar señales de riesgo y decidir confirmación de cambios
  → 7: recuperar alternativas similares con LSH y HNSW
  → 8: aplicar orden cerrada una sola vez y consultar complementos/comunidades
  → 9: mostrar Top-K, ventas y señales de alerta con trazabilidad
```

El intento de pago se cuenta al procesar su propio evento, no otra vez al procesar la compra que lo referencia. Las entidades señaladas se consultan cuando correspondan. Una búsqueda o vista puede consultar las recomendaciones existentes sin modificar el grafo. Una operación retenida conserva salida de alerta y no confirma compras ni inventario. El servicio podrá leer índices confirmados después de la decisión de la etapa 6.

Preparar dos escenarios complementarios: una compra válida que llegue a las diez etapas y cambie el grafo, y una ráfaga de intentos con verificaciones de riesgo que produzca una alerta. Persistir por `event_id` las entradas, decisiones y salidas utilizadas por etapas posteriores para demostrar integración, no solo ejecuciones aisladas.

## Arquitectura del repositorio y notebooks

GitHub será el medio de entrega y colaboración. Los notebooks serán interfaces de exploración, demostración y análisis; importarán la implementación desde módulos Python, evitando depender del estado de celdas ejecutadas manualmente.

```text
proyecto/
├── README.md
├── requirements.txt
├── configs/                     # Semillas, generación, ventanas y benchmarks
├── src/
│   ├── data/                    # Esquema, validación y enriquecimiento
│   ├── simulation/              # Reproductor y escenarios
│   ├── structures/              # Estructuras base y algoritmos
│   ├── pipeline/                # Etapas, coordinación y trazabilidad
│   ├── service/                 # Consultas, Top-K y panel
│   └── evaluation/              # Métricas y comparaciones
├── scripts/                     # Generación, ejecución y benchmarks largos
├── notebooks/
│   ├── 01_validacion_data.ipynb
│   ├── 02_demo_pipeline.ipynb
│   └── 03_analisis_resultados.ipynb
├── tests/                       # Invariantes, integración y casos controlados
├── data/                        # Datos locales; archivos grandes fuera de Git
├── results/                     # Métricas y manifiestos de ejecución
└── docs/                        # Informe PDF, diagrama y presentación
```

Las ejecuciones de 10M se lanzarán mediante scripts que guarden métricas y progreso; los notebooks consumirán esos resultados. La interfaz inicial será el notebook de demo y un servicio local invocable desde él. No se requiere publicar un sitio para demostrar el pipeline.

El README incluirá instalación, obtención de la fuente, comandos reproducibles, configuración, limitaciones y tabla de roles/contribuciones. No se subirán CSV masivos ni salidas voluminosas de notebooks; se documentará cómo regenerarlos y verificar sus versiones.

## Experimentación y análisis

### Dos niveles de evaluación

1. **Pipeline completo:** ejecutar datasets de 1K, 10K, 100K, 1M y 10M eventos; medir throughput, latencia, memoria, colas y salidas funcionales.
2. **Estructuras y etapas fijas:** generar entradas con las escalas exigidas por el enunciado. Diez millones de eventos no equivalen a diez millones de claves, conjuntos, vectores o nodos. Cuando el histórico no alcance, generar entradas sintéticas coherentes con las propiedades del dominio, sin presentarlas como datos observados.

| Componente | Unidad de escala y contexto que debe reportarse |
|---|---|
| FIFO y heap | Eventos procesados y ocupación máxima; separar volumen de entrada de tamaño residente. |
| Hash table, B+Tree y LRU | Claves/entradas; para LRU, capacidad y tasa de aciertos. |
| Matriz dispersa | Dimensiones y número de valores no nulos. |
| Bloom Filter | Claves distintas insertadas, consultas y proporción de consultas ausentes. |
| Count-Min Sketch | Actualizaciones, claves distintas, distribución de frecuencias y ventanas. |
| MinHash + LSH | Cantidad de conjuntos, cardinalidades, universo y parámetros de firmas/bandas. |
| KD-Tree y HNSW | Cantidad de puntos/vectores, dimensiones, métrica y consultas. |
| Grafo | Nodos, aristas, densidad, pesos y componentes conectadas. |

El enunciado no especifica si la escala del grafo corresponde a nodos o aristas. Se deberá validar esa interpretación con el docente y registrar la decisión antes de ejecutar los experimentos mayores. Hasta entonces, reportar ambas cantidades y preparar el generador con parámetros independientes.

### Comparaciones obligatorias

| Familia | Comparación y métricas |
|---|---|
| Bloom Filter | Hash set exacto: tiempo, memoria y tasa de falsos positivos sobre claves realmente ausentes. |
| Count-Min Sketch | Diccionario exacto: tiempo, memoria y error de frecuencia; medir también calidad de alertas simuladas. |
| MinHash + LSH | Jaccard exacto por fuerza bruta: tiempo, memoria y calidad de recuperación. |
| HNSW | KNN exacto/fuerza bruta en el mismo espacio: tiempo, recall@K y memoria. |
| Personalized PageRank | Ranking por grado ponderado: tiempo y diferencias en el ranking; distinguir consulta personalizada y ranking global con personalización uniforme. |
| Louvain | Label Propagation sobre el mismo grafo: modularidad, tiempo, número/tamaños de comunidades y estabilidad. |

### Protocolo reproducible

- Guardar semilla, configuración, versión de datos y código, plataforma, CPU, RAM y versiones de dependencias.
- Separar tiempos de construcción, actualización y consulta. No incluir generación de datos en una medición de consulta sin indicarlo.
- Realizar 100 repeticiones cuando sea viable y reportar promedio, desviación estándar y número efectivo de repeticiones. Para 10M, justificar menos repeticiones por tiempo o memoria; documentar también otras limitaciones si aparecen.
- Definir cuándo se reinicia el estado entre repeticiones; distinguir caché fría y caliente y excluir calentamientos de las estadísticas medidas.
- Medir memoria actual y pico con `tracemalloc` y, cuando existan extensiones nativas, una medición de memoria del proceso que cubra sus asignaciones.
- Graficar escalabilidad log-log y contrastar resultados con las complejidades esperadas.
- Usar separación temporal entre construcción de representaciones y evaluación para evitar información futura. Calcular la referencia exacta sobre todo el universo elegible indexado por el método aproximado, con las mismas consultas y filtros; no limitarla a los candidatos que este recuperó.
- Registrar limitaciones de escala con evidencia. Si una corrida no cabe en memoria o no termina en el presupuesto disponible, reportarlo; no sustituirla silenciosamente por un tamaño menor.

## Demostración y verificaciones

La demo de 3–4 minutos mostrará una ejecución real del pipeline desde el notebook:

1. Ingresar eventos de distinta prioridad y un caso de orden con varios productos.
2. Seguir un `event_id` válido por las diez etapas hasta una recomendación, alerta o Top-K.
3. Reenviar un evento y comprobar que no duplica compras ni aristas.
4. Mostrar consultas del Bloom Filter, verificación exacta y estimaciones del CMS frente al conteo real.
5. Comparar resultados aproximados con la referencia exacta y mostrar recall@K.
6. Mostrar co-compra, ranking de influencia, comunidades y el resultado en el servicio.

Las verificaciones automatizadas cubrirán invariantes relevantes: referencias de órdenes y devoluciones, identidad de duplicados, idempotencia, prioridades, consistencia de índices y una ejecución integrada con salida observable. Los resultados de gran escala se generarán previamente y se presentarán desde archivos persistidos, con sus comandos de reproducción.

## Entregables y secuencia de trabajo

1. Definir esquema, reglas de generación, ventanas y manifiestos; resolver la unidad de escala del grafo.
2. Implementar generador y validación; producir versiones de 1K a 10M con composición conocida.
3. Construir un recorrido mínimo integrado de diez etapas antes de ampliar las corridas.
4. Incorporar representaciones, estructuras y comparaciones exactas; verificar consistencia y trazabilidad.
5. Ejecutar experimentos, guardar métricas y elaborar gráficos e interpretación.
6. Preparar notebooks, README, diagrama, informe PDF de 8–12 páginas y presentación de 10–15 diapositivas.

### Tareas de implementación de las etapas 6–8

- [ ] Definir configuración versionada para claves, ventanas, umbrales, Bloom, CMS, LSH, HNSW y grafo.
- [x] Implementar registro exacto de entidades señaladas y generador reproducible de intentos de pago.
- [x] Implementar Bloom Filter, actualización/reconstrucción y verificación exacta de positivos.
- [x] Implementar CMS por bloques, avance temporal, expiración y contador exacto de referencia/verificación.
- [x] Exponer API `/fraude`, servicio compartido y adaptador por lotes con persistencia CSV recuperable.
- [x] Incluir datos de ejemplo, pruebas y verificación 1K/10K de etapa 6, con 100 repeticiones de comparaciones de estructuras en memoria.
- [ ] Integrar `risk_signals` con confirmación de cambios y panel de alertas.
- [ ] Construir conjuntos de atributos y referencia Jaccard; implementar MinHash + LSH.
- [ ] Construir vectores versionados y referencia KNN exacta; implementar HNSW.
- [ ] Integrar ambas listas de candidatos con filtros y regla de fusión del servicio.
- [ ] Implementar cierre de órdenes, deduplicación por orden y actualización idempotente de aristas.
- [ ] Implementar Personalized PageRank y ranking global con comparación por grado ponderado.
- [ ] Implementar Louvain y comparación con Label Propagation sobre instantáneas comunes.
- [ ] Incorporar versiones del grafo y consumo de complementos/comunidades en la etapa 9.
- [ ] Verificar los criterios de aceptación con casos controlados e integración de diez etapas.
- [ ] Ejecutar benchmarks por escala y guardar configuración, métricas, memoria y calidad.

El repositorio incluirá la tabla de responsables por etapa y contribuciones, coherente con el historial de Git. Cada integrante asumirá al menos dos etapas o una familia del bloque avanzado y deberá poder explicar el funcionamiento del pipeline completo.

Para las etapas 0–5 se documentarán función, complejidad y justificación frente a alternativas. Para las etapas 6–8 se investigarán las cinco familias avanzadas con fundamentos, funcionamiento interno, complejidad temporal y espacial, límites, trade-offs, papers originales, implementaciones de referencia y evidencia experimental.
