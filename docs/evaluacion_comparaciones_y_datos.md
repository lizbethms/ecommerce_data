# Evaluación de comparaciones obligatorias y suficiencia de datos

Fecha: 25 de octubre de 2026. Evaluación del diseño y de los artefactos locales; no es un benchmark de las etapas 6–8.

## Dictamen

Los componentes propuestos en `Plan_proyecto.md` son adecuados para cubrir las comparaciones obligatorias. El esquema de eventos aporta buena parte de las claves necesarias, pero **los campos por sí solos y los escenarios generados actualmente no son suficientes para evaluar esas comparaciones**. Faltan conjuntos de referencia, representaciones derivadas, estados de orden, consultas experimentales y escenarios con volumen y diversidad controlados.

Conviene conservar el contrato de eventos y ampliar el generador y sus entidades auxiliares. No hace falta incluir vectores, listas de riesgo o comunidades completas en cada evento.

Se revisaron el plan, el enunciado local `Proyecto EDA - 2026-2.docx`, `src/data/schema.py`, `src/data/prepare.py`, la configuración y los datasets preparados 1K y 10K. El enunciado exige comparaciones probabilísticas/exactas, conjuntos/fuerza bruta, ANN/KNN y comunidades sobre un mismo grafo. El plan concreta esas alternativas y añade grado ponderado como referencia del ranking.

## Evidencia de los datasets existentes

Conteos consultados directamente en `data/prepared/{1K,10K}/entities.sqlite`, abiertas en modo de solo lectura:

| Propiedad | 1K | 10K | Implicación |
|---|---:|---:|---|
| Eventos totales | 1.000 | 10.000 | No equivalen a elementos de cada estructura. |
| Productos de catálogo | 532 | 4.144 | Escala disponible para conjuntos y vectores por producto. |
| Intentos de pago | 5 | 5 | Aumentar el dataset no aumenta este escenario. |
| Dispositivos en pagos | 1 | 1 | No hay diversidad para evaluar colisiones y cargas por clave. |
| Pagos etiquetados como anomalía | 2 | 2 | Son fallos de pago; no constituyen por sí solos una ráfaga de alta frecuencia. |
| Órdenes | 12 | 116 | Incluyen agrupaciones históricas sintéticas. |
| Compras únicas, sin reenvío | 14 | 122 | Se mantienen separadas de la copia duplicada. |
| Órdenes con varios productos | 2 | 5 | Todas tienen solo dos productos distintos. |
| Aristas potenciales de co-compra | 2 | 5 | Pares obtenidos agrupando compras únicas por orden. |
| Productos incidentes en esas aristas | 4 | 10 | Las aristas no comparten extremos; todos los pesos son 1. |
| Productos sin `category_code` | 221 | 1.807 | Se conserva `category_id`, pero hay que definir su uso como atributo. |
| Productos sin `brand` | 87 | 852 | Hay que excluir atributos ausentes de los conjuntos. |
| Compras que referencian `payment_attempt_id` | 0 | 0 | La relación actual con el pago es indirecta por orden. |
| Filas de inventario / con stock positivo | 11 / 1 | 97 / 1 | El filtro de disponibilidad puede dejar casi sin candidatos al servicio. |

Las aristas anteriores son una reconstrucción exploratoria, **no un grafo confirmado por el pipeline**: todavía faltan el cierre de órdenes y la etapa 8. La tabla `payments` tiene tres registros en cada dataset porque guarda únicamente pagos exitosos por orden; los cinco intentos están en los eventos.

El generador reserva siempre 13 eventos: cinco pagos, cuatro compras, una devolución, una reseña, una búsqueda y un reenvío. Este bloque es útil para integración inicial, pero no escala las pruebas avanzadas.

## Evaluación de las seis comparaciones

| Comparación | Adecuación de componentes | Suficiencia actual y acciones necesarias |
|---|---|---|
| Bloom Filter vs. hash set | Correcta para pertenencia a entidades señaladas. El conjunto exacto también permite clasificar los resultados del filtro. | Los IDs existen, pero falta un registro exacto de entidades señaladas y consultas presentes/ausentes conocidas. Generar ambos grupos, claves tipadas, distintas capacidades y cargas. Medir falsos positivos solo entre consultas realmente ausentes. |
| Count-Min Sketch vs. diccionario | Correcta para frecuencia por dispositivo y ventana, con referencia exacta bajo los mismos límites. | `payment_attempt_id`, `device_id` y `event_time` bastan como campos de entrada; cinco intentos de un dispositivo no bastan como carga experimental. Generar muchas claves, distribuciones uniformes y sesgadas, ráfagas y expiración. |
| MinHash + LSH vs. Jaccard exhaustivo | Correcta para conjuntos de atributos; reordenar candidatos con Jaccard exacto conserva una referencia clara. | Categoría y marca permiten un experimento básico. Faltan los conjuntos materializados, su regla de construcción y consultas. Muchos conjuntos pequeños o idénticos producen empates; medir cardinalidades, cobertura y patrones repetidos. |
| HNSW vs. KNN exhaustivo | Correcta si usa los mismos vectores, métrica, universo y filtros. | Hay datos para construir vectores básicos; todavía no existen sus transformaciones, versiones ni consultas de evaluación. El KD-Tree solo sirve como referencia comparable si opera sobre exactamente la misma representación y métrica. |
| Personalized PageRank vs. grado ponderado | Adecuada para contrastar influencia local con popularidad estructural; no mide por sí sola la calidad comercial de recomendaciones. | Los pares actuales son demasiado triviales: el grado de todos los nodos incidentes es 1. Generar órdenes solapadas, pesos repetidos, cadenas y puentes. Registrar semillas de personalización, instantánea y criterios de desempate. |
| Louvain vs. Label Propagation | Adecuada para contrastar comunidades en el mismo grafo. | Dos o cinco pares aislados no permiten una evaluación informativa de comunidades. Crear grafos con grupos, conexiones internas y puentes; comparar modularidad bajo la misma convención de pesos, tiempo, tamaños y estabilidad entre semillas. |

### Precisiones experimentales

- **Bloom:** el registro de riesgo no se obtiene de `is_injected_anomaly`. Su pertenencia debe definirse independientemente y, si cambia durante el replay, tener vigencia temporal. Reportar memoria del filtro, del conjunto y del sistema que usa ambos. Una FPR observada de cero con pocas consultas no demuestra una tasa objetivo pequeña.
- **CMS:** el plan fija un umbral de 20 intentos por dispositivo en cinco bloques de un minuto. Con cinco intentos totales, el conteo real nunca alcanza ese umbral. Preparar casos de 19, 20 y 21 intentos dentro de los mismos bloques, dispositivos benignos, saltos de tiempo, eventos tardíos y reenvíos. Una estimación por colisión que alcance 20 debe ser descartada por el verificador si el conteo real es menor.
- **Etiquetas:** un pago fallido no implica necesariamente alta frecuencia ni pertenencia al registro señalado. Definir verdad de referencia por escenario y regla evaluada, en un archivo de evaluación separado. No introducir etiquetas, IDs de escenario o prioridades que revelen el resultado esperado en los vectores o detectores.
- **Jaccard:** usar tokens con prefijos, por ejemplo `category_id:...`, `category_code:...`, `brand:...`; decidir si incluir simultáneamente ID y código de categoría sobrerrepresenta esa señal. No usar `product_id` ni un token común `unknown`. Para conjuntos vacíos, definir exclusión o fallback. El atributo `uso` mencionado en el plan no está generado; sería una ampliación sintética opcional.
- **Vecindad:** `price` textual debe transformarse a una característica numérica documentada. Los IDs categóricos no deben convertirse en coordenadas ordinales arbitrarias. Añadir comportamiento es posible a partir del histórico previo al corte; ajustar codificadores y normalizadores solo con ese periodo. Guardar tratamiento de productos nuevos y vectores degenerados.
- **Calidad:** MinHash necesita error de estimación y calidad de recuperación; HNSW necesita `recall@K`. Usar consultas comunes con la referencia exacta sobre todo el universo elegible. Documentar empates, exclusión del propio producto y consultas con menos de K vecinos.
- **Ranking:** comparar ranking global con personalización uniforme y ranking personalizado por separado. El grado ponderado no es una verdad de referencia de relevancia. Usar coincidencia en Top-K y, con una convención de empates, correlación de rankings; si se evalúa utilidad, añadir compras futuras reservadas como evaluación independiente.
- **Comunidades:** la estabilidad requiere varias ejecuciones y una medida entre particiones que no dependa del número arbitrario asignado a cada comunidad. Si se generan comunidades conocidas, pueden servir como referencia adicional, conservando por separado su procedencia sintética.

## Revisión del evento del ejemplo

El registro presentado es válido como **intento de pago sintético**, según las validaciones actuales:

- Tiene identidad estable, tiempo del dominio, usuario, sesión, orden, intento, dispositivo, medio de pago y estado.
- `quantity: null`, `query: null`, `rating: null` y `original_purchase_event_id: null` son apropiados para este tipo. La cantidad será obligatoria en compras/devoluciones, no en todo pago.
- `delivery_type: scheduled` tiene una fecha posterior al evento. La prioridad 0 es coherente con la regla actual, que da prioridad especial a express y a pagos fallidos; falta definir qué sucede al acercarse el vencimiento de una entrega programada.
- `price: "515.67"` conserva precisión monetaria, pero representa el precio asociado al producto; no acredita el monto total pagado por una orden de varios productos. Si se comparan importes, añadir `payment_amount` y `currency` al pago o a su entidad asociada, con reglas de suma.
- `event_time` de 2019 e `ingested_at` de 2026 son coherentes con un replay histórico. Su diferencia no mide latencia de procesamiento. Usar reloj monotónico para duraciones; `processing_times` aporta trazabilidad de instantes.
- `stage_results` contiene solo la etapa 0. El sobre no demuestra todavía integración, resultados ni rendimiento de las etapas posteriores.
- `is_injected_anomaly: false` es metadato de evaluación. No prueba que el dispositivo esté fuera del registro de riesgo ni sustituye su consulta.

Un pago exitoso tampoco prueba que la orden esté cerrada, que estén disponibles todas sus líneas o que las compras hayan sido confirmadas por el pipeline. El ejemplo no permite actualizar por sí solo la co-compra.

## Contratos y artefactos que faltan

| Artefacto | Contenido mínimo | Ubicación sugerida |
|---|---|---|
| Registro de riesgo | Tipo e ID de entidad, pertenencia, versión y vigencia si cambia. | Tabla o archivo independiente; fuera de las señales del detector. |
| Ciclo de orden | Estado, líneas/productos, cantidades, confirmación y señal inequívoca de cierre. | Entidad `orders` y evento de cierre o protocolo equivalente. |
| Asociación compra–pago | Intento exitoso que respalda cada orden sintética confirmada. | Referencia desde orden/compra; permitir desconocido explícito en compras históricas. |
| Conjuntos | Producto, tokens, versión, fecha de corte y política de nulos. | Artefacto de características. |
| Vectores | Producto, valores, dimensiones, transformaciones, métrica y versión. | Artefacto de características y manifiesto. |
| Carga de consultas | Consultas de pertenencia, claves de frecuencia, productos consulta y semillas de ranking. | Dataset experimental reproducible separado de la construcción. |
| Referencias exactas | Pertenencia, conteos por bloque, vecinos exactos y snapshot de grafo. | Resultados de evaluación con versión de datos. |
| Disponibilidad | Cobertura del catálogo, stock inicial y política temporal. | Inventario sintético independiente del inventario mínimo inferido. |

La tabla de órdenes actual no tiene estado, líneas esperadas ni fecha de cierre. Si se elige un evento `order_closed`, habrá que ampliar `TYPES` y su validador; otra opción es un protocolo explícito de cierre por ventana con control de eventos tardíos. Un marcador de fin del replay no basta para demostrar el comportamiento de un stream continuo.

Las compras históricas no tienen pago observado: no deben rechazarse automáticamente ni presentarse como pagadas. Definir su política de admisión y distinguirla del ciclo sintético controlado.

El catálogo SQLite conserva la última observación del prefijo completo. Cargarlo al inicio del replay podría revelar precios o atributos posteriores al evento procesado. Construir representaciones a un corte anterior a las consultas o actualizar el catálogo de forma incremental.

El inventario actual repone solo lo necesario antes de cada compra y deja stock casi siempre en cero. Es válido como balance inferido, pero no como escenario de oferta para recomendar todo el catálogo: faltan existencias para productos vistos pero nunca comprados. Definir stock positivo, agotamientos y reposiciones simuladas con tiempos coherentes.

## Cambios prioritarios y aceptación

1. **Completar integración:** definir confirmación/cierre, asociación con pago y disponibilidad; conservar idempotencia por evento, intento y orden. Exigir el mismo grafo tras un reenvío.
2. **Ampliar riesgo:** generar registro señalado, consultas negativas y positivas, dispositivos diversos y ventanas que crucen el umbral. Mostrar una alerta verificada y un caso expirado. Duplicar también un intento de pago: el reenvío actual es de compra y no prueba deduplicación del CMS.
3. **Materializar similitud:** producir conjuntos/vectores versionados y consultas con referencias exhaustivas; comparar métodos bajo filtros y cortes idénticos.
4. **Ampliar co-compra:** añadir órdenes de tres o más productos, pares repetidos, solapamiento y comunidades conectadas por puentes. Conservar casos pequeños con pesos verificables manualmente.
5. **Separar escalas:** parametrizar número de claves, conjuntos, vectores, nodos y aristas además del número de eventos. Generar cargas 1K–10M por unidad exigida, con manifiestos; resolver con el docente si la escala del grafo significa nodos o aristas, como ya advierte el plan.
6. **Medir:** separar construcción, actualización y consulta; registrar memoria de estructuras y verificadores, calidad, semillas, versiones y repeticiones efectivas. Justificar cualquier reducción de escala o repeticiones.

Hasta completar estos puntos, los datos permiten validar preparación y etapa 0, además de iniciar prototipos básicos de similitud. No sustentan todavía conclusiones comparativas sobre precisión, escalabilidad o utilidad de las etapas obligatorias.
