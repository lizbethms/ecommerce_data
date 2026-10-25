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

Este documento define el diseño previsto; no implica que el generador, el pipeline o los benchmarks ya estén implementados.

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
| 8 [FIJA] | Grafo del dominio / S8–S9 | PageRank y Louvain | Actualizar co-compra por orden sintética y producir influencia y comunidades. |
| 9 | Servicio y visualización / transversal | Top-K y Trie | Combinar candidatos, popularidad y señales del grafo para recomendaciones, búsquedas, autocompletado y paneles. |

### Integración y estado

Cada evento circulará en un sobre con `event_id`, referencias a entidades, resultados de etapas y tiempos de procesamiento. La salida de cada etapa será entrada de la siguiente; un evento puede aportar contexto o consultar un índice aunque no actualice todas las estructuras.

Las etapas 3–5 prepararán cambios o consultarán estado confirmado. Las decisiones de la etapa 6 determinarán qué actualizaciones se confirman y alimentan los índices, las recomendaciones y el grafo. Esto requiere un mecanismo explícito de confirmación o actualizaciones idempotentes para no contabilizar dos veces un reenvío.

Un evento rechazado por validación o identificado como duplicado conservará una salida observable de rechazo o descarte. Para la demostración se elegirá además un evento válido que atraviese las diez etapas hasta el servicio.

### Representaciones para similitud y grafo

- **Matriz usuario–producto:** interacciones ponderadas por tipo, con pesos configurables. Analizar cómo la mayor cantidad de vistas afecta las señales de compra.
- **Conjuntos para MinHash:** usuarios que interactuaron con cada producto dentro de una ventana; comparar Jaccard estimado con Jaccard exacto.
- **Vectores para HNSW:** características de producto derivadas de atributos y comportamiento. Ajustar transformaciones con el periodo de referencia, sin incorporar información futura de evaluación.
- **KNN:** usar el mismo espacio y métrica al comparar HNSW con búsqueda exacta. El KD-Tree podrá usar una representación de baja dimensión; si difiere de la de HNSW, reportarlo como experimento separado y usar fuerza bruta en el espacio de HNSW.
- **Grafo de co-compra:** productos como nodos y aristas no dirigidas ponderadas por el número de órdenes distintas compartidas. Contabilizar cada par una vez por orden, sin bucles ni doble conteo por reenvíos. Definir la finalización de órdenes y la ventana temporal.
- **Frecuencias:** definir clave, ventana, umbral y política de expiración para CMS; por ejemplo, intentos de pago por usuario en una ventana. Un CMS simple no elimina por sí mismo eventos vencidos: usar ventanas por bloques o rotación documentada.
- **Pertenencia:** un positivo del Bloom Filter no prueba identidad ni fraude. Verificar con un registro exacto antes de descartar una operación legítima o bloquear una cuenta.

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
| PageRank | Ranking por grado ponderado o frecuencia: tiempo y diferencias en el ranking. |
| Louvain | Label Propagation sobre el mismo grafo: modularidad, tiempo, número/tamaños de comunidades y estabilidad. |

### Protocolo reproducible

- Guardar semilla, configuración, versión de datos y código, plataforma, CPU, RAM y versiones de dependencias.
- Separar tiempos de construcción, actualización y consulta. No incluir generación de datos en una medición de consulta sin indicarlo.
- Realizar 100 repeticiones cuando sea viable y reportar promedio, desviación estándar y número efectivo de repeticiones. Para 10M, justificar menos repeticiones por tiempo o memoria; documentar también otras limitaciones si aparecen.
- Definir cuándo se reinicia el estado entre repeticiones; distinguir caché fría y caliente y excluir calentamientos de las estadísticas medidas.
- Medir memoria actual y pico con `tracemalloc` y, cuando existan extensiones nativas, una medición de memoria del proceso que cubra sus asignaciones.
- Graficar escalabilidad log-log y contrastar resultados con las complejidades esperadas.
- Usar separación temporal entre construcción de representaciones y evaluación para evitar información futura. Calcular la referencia exacta sobre el mismo conjunto de candidatos que el método aproximado.
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

El repositorio incluirá la tabla de responsables por etapa y contribuciones, coherente con el historial de Git. Cada integrante asumirá al menos dos etapas o una familia del bloque avanzado y deberá poder explicar el funcionamiento del pipeline completo.

Para las etapas 0–5 se documentarán función, complejidad y justificación frente a alternativas. Para las etapas 6–8 se investigarán las cinco familias avanzadas con fundamentos, funcionamiento interno, complejidad temporal y espacial, límites, trade-offs, papers originales, implementaciones de referencia y evidencia experimental.
