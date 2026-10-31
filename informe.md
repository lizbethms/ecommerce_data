UNIVERSIDAD DE INGENIERÍA Y TECNOLOGÍA
ESCUELA DE POSGRADO






PROYECTO: Estructuras de datos avanzadas en un pipeline de comercio electrónico

AUTOR(ES)
Mamani Salce, Lizbeth Mercedes
Vargas García, Karen
Trelles Vizcarra, Nicolas
Campos Arteaga, Jhon 



DOCENTE
Heider Sánchez

CURSO
Estructuras de Datos y Algoritmos (MCD8006) - Teoría - 1




Lima – Perú
2026





Resumen

Se implementó y analizó un pipeline de eventos de comercio electrónico de diez etapas, sobre datos reales de REES46 enriquecidos con un 20 % de eventos sintéticos (pagos, órdenes y casos controlados). Un evento entra por la API, espera en una FIFO acotada, se ordena y deduplica en lotes y se despacha a siete servicios; una orden (intento de pago más compras) recorre las diez etapas y produce una salida observable en cada una. La campaña experimental se ejecutó en una sola máquina (Windows 10, AMD Ryzen 9 5900HS, 16 GB, Python 3.14.2, semilla 2026) con 1K, 10K y 100K eventos, 100 repeticiones por consulta y tres construcciones por estructura.

HNSW respondió en alrededor de 1 ms en las tres escalas frente a 1,7 / 13,5 / 76,9 ms de la fuerza bruta, con recall@10 de 0,85 / 0,68 / 0,63. MinHash/LSH fue unas 900 veces más rápido que Jaccard exhaustivo en 100K, pero su recall@10 fue bajo (0,16) con 16 bandas × 4 filas; el barrido de parámetros lo explica por la escasez de candidatos y muestra que 32 × 2 eleva el recall a 0,61. Bloom mantuvo una tasa de falsos positivos de 0,97 % frente al 1 % objetivo y CMS acotó su error dentro de ε·N. En comunidades, Louvain superó a Label Propagation en modularidad (0,793 frente a 0,758 en 100K) y estabilidad entre semillas (NMI 0,984 frente a 0,920), mientras que Label Propagation fue unas dos veces más rápido.

1. Contexto y objetivo

Se eligió el escenario de comercio electrónico para integrar ingesta, prioridades, búsqueda, detección de actividad sospechosa, similitud y análisis de co-compra. Se parte de eventos reales enriquecidos con un componente sintético que incorpora pagos, órdenes y casos controlados. Se busca que la salida de una etapa alimente funciones posteriores y produzca resultados observables en el servicio.

La unidad principal de escala es el evento procesado. El número de claves de pago, vectores, conjuntos y nodos del grafo se informa por separado: no se interpreta que 100K eventos equivalgan a 100K elementos en cada índice.

2. Arquitectura del pipeline

| Etapa | Estructura | Función |
|---|---|---|
| 0 | FIFO acotada | Recibe eventos en la API y aplica contrapresión cuando se llena. |
| 1 | Merge sort y tabla hash | Ordena cada lote y descarta duplicados. |
| 2 | MinHeap con política EDF | Ordena alertas y órdenes por urgencia. |
| 3 | Tabla hash, matriz dispersa y LRU | Mantiene estado, interacciones y caché. |
| 4 | B+Tree | Resuelve búsquedas puntuales y rangos por precio y tiempo. |
| 5 | KD-Tree | Proporciona KNN exacto como línea base. |
| 6 | Bloom y CMS por ventanas | Filtra claves señaladas y estima frecuencias de pago. |
| 7 | MinHash/LSH y HNSW | Propone vecinos de conjuntos y de vectores. |
| 8 | Grafo, PageRank, Louvain y Label Propagation | Calcula influencia y comunidades de co-compra. |
| 9 | Trie, Top-K, API y panel | Entrega autocompletado, rankings y métricas. |

`POST /eventos/lote` deja cada evento en una `BoundedFIFO` (etapa 0). Si la cola está llena, la petición espera. Un consumidor vacía la cola en lotes que la ingesta ordena y deduplica (etapa 1) y despacha en orden temporal a catálogo, fraude, priorización, co-compra, recomendación, búsqueda y panel. Cada respuesta incluye el recorrido de etapas del evento. El script `scripts/recorrido_evento.py` envía una orden (un intento de pago fallido y dos compras) y verifica que, en conjunto, recorre las etapas 0–9 con una salida observable por etapa: ocupación de la FIFO, deduplicación de un reenvío, posición en el heap, acierto de la caché LRU, ventas por rango en el B+Tree, vecinos exactos del KD-Tree, alerta de fraude, recall de HNSW, cross-selling del grafo y autocompletado. El diagrama interactivo está en `docs/arquitectura_pipeline.html`.

El B+Tree implementado reside en memoria. Su comportamiento no permite atribuir rendimiento de disco ni satisfacer por completo la exigencia de un índice de disco.

3. Estructuras base: función, coste y elección

| Estructura | Coste esperado | Pendiente log-log observada | Justificación |
|---|---|---|---|
| FIFO | O(1) por operación; memoria O(C) | 0,97 (paso de n eventos) | Conserva el orden y limita la ocupación. |
| Merge sort | O(n log n) | 1,14 | Orden estable para deduplicar por adyacencia. |
| Tabla hash | O(1) esperado | Construcción 1,08; consulta ≈ 0,00 | Lookup constante sujeto a carga y colisiones. |
| MinHeap | O(log n) por operación | Construcción 1,23; pushpop 0,12 | Actualiza prioridades sin reordenar la lista. |
| Matriz dispersa | O(nnz) memoria | Construcción 1,08; consulta 0,10 | Almacena solo interacciones observadas. |
| LRU | O(1) | Construcción 1,01; consulta ≈ 0 | Aprovecha localidad con capacidad fija (256). |
| B+Tree | O(log_m n) más salida | Construcción 1,17; búsqueda 0,11 | Sostiene rangos ordenados que el hash no ofrece. |
| KD-Tree | Construcción O(n log² n) | Construcción 1,05; KNN 0,62 | KNN exacto; la consulta se degrada en 19 dimensiones. |
| Trie | O(L) más salida | Construcción 0,77; completar 0,46 | Atiende prefijos; la consulta crece con el subárbol. |
| Top-K | O(n log k) | 0,97 | Ranking parcial sin ordenar todo. |

Las pendientes se ajustaron por mínimos cuadrados sobre log10(tiempo) frente a log10(n), con n la carga real de cada estructura en 1K, 10K y 100K. Una pendiente cercana a 1 corresponde a crecimiento lineal (O(n) y, en la práctica, O(n log n)); cercana a 0, a coste constante o logarítmico. Las construcciones observadas concuerdan con lo esperado. El KNN del KD-Tree (0,62) confirma su degradación hacia O(n) en 19 dimensiones.

4. Filtrado probabilístico

Bloom Filter

Se representa la pertenencia con bits y varias funciones hash. Inserción y consulta cuestan O(k), con memoria fijada por la capacidad configurada. Un negativo es concluyente; un positivo se verifica contra un registro exacto antes de una decisión crítica. Se eligió por ahorro de memoria frente a un conjunto exacto, a cambio de falsos positivos y una verificación adicional.

| Escala | Claves | Bits / hashes | FP observada (100.000 ausentes) | FP teórica | Falsos negativos | Memoria Bloom | Memoria `set` |
|---|---|---|---|---|---|---|---|
| 1K | 30 | 293 / 7 | 0,968 % | 0,918 % | 0 | < 0,001 MiB | 0,002 MiB |
| 10K | 218 | 2.099 / 7 | 1,013 % | 0,983 % | 0 | 0,001 MiB | 0,008 MiB |
| 100K | 2.175 | 20.849 / 7 | 0,968 % | 1,004 % | 0 | 0,003 MiB | 0,125 MiB |

La tasa observada coincide con la teórica (1 − e^(−kn/m))^k y con el objetivo de 1 %. En 100K, Bloom ocupó unas 40 veces menos memoria que el conjunto exacto, pero cada consulta costó 3,6 µs frente a 0,03 µs del `set` de Python (unas 120 veces más): el ahorro es de memoria, no de tiempo, porque el `set` está implementado en C y Bloom en Python.

Count-Min Sketch

Se actualizan d contadores y se estima una frecuencia con el mínimo de las filas. Para incrementos no negativos el CMS nunca subestima, y con probabilidad 1 − δ el error es menor que ε·N, con ε = e/ancho y δ = e^(−profundidad). Se emplean cuatro filas y ancho 1.024 (ε = 0,0027, δ = 0,018). La variante temporal usa seis bloques de 100 segundos para una ventana de 600 segundos.

| Escala | Actualizaciones N | Claves | Error absoluto medio | RMSE | Error máximo | Cota ε·N | Claves dentro de la cota |
|---|---|---|---|---|---|---|---|
| 1K | 81 | 30 | 0 | 0 | 0 | 0,2 | 100 % |
| 10K | 681 | 218 | 0 | 0 | 0 | 1,8 | 100 % |
| 100K | 6.132 | 2.175 | 1,30 | 2,00 | 9 | 16,3 | 100 % |

El error medido sobre todas las claves reales de pago crece con N pero se mantuvo dentro de la cota en todas las claves. El CMS ocupa 0,032 MiB fijos; con estas cargas pequeñas el `Counter` exacto todavía es comparable (0,056 MiB en 100K), y la ventaja del CMS aparece cuando el número de claves distintas crece. Cada estimación costó 3,3 µs frente a 0,045 µs del `Counter`. El CMS por ventanas no mostró error al final del flujo en las tres escalas.

Se consideran pybloomfiltermmap3 y Apache DataSketches como implementaciones de referencia para Bloom y CMS. En las mediciones se utilizó la implementación del proyecto y se contrastó con estructuras exactas de Python.

5. Similitud aproximada

Conjuntos: MinHash y LSH

Se estima Jaccard con 64 permutaciones MinHash y se recuperan candidatos mediante bandas de filas. Se compara con Jaccard exhaustivo sobre todos los conjuntos del mismo índice. El recall se calcula aceptando empates en el límite.

| Escala | Conjuntos | Jaccard exhaustivo (ms) | MinHash/LSH 16×4 (ms) | Recall@10 (16×4) | Memoria índice LSH | Memoria mapa exacto |
|---|---|---|---|---|---|---|
| 1K | 455 | 0,41 ± 0,04 | 0,021 ± 0,004 | 0,20 | 2,7 MiB | 0,01 MiB |
| 10K | 3.471 | 4,11 ± 0,27 | 0,034 ± 0,007 | 0,32 | 20,6 MiB | 0,10 MiB |
| 100K | 18.008 | 36,94 ± 3,14 | 0,041 ± 0,012 | 0,16 | 113,4 MiB | 0,40 MiB |

El barrido de bandas × filas sobre las mismas firmas explica el recall bajo. Con 16 × 4 cada consulta recibe solo 2,5–4 candidatos, porque los Jaccard de los vecinos reales son bajos y la probabilidad de colisión 1 − (1 − s^r)^b cae rápido con r. Con **32 × 2** el recall@10 sube a 0,59 / 0,52 / 0,61 con unos 8 candidatos y menos de 0,06 ms por consulta; con 8 × 8 y 4 × 16 baja a 0,15–0,21. Se recomienda 32 × 2 para este dominio.

Vectores: HNSW y KNN exacto

Se navega un grafo jerárquico de vecinos (M = 8, ef de construcción 48, ef de búsqueda 48) sobre vectores de 19 dimensiones con distancia euclidiana. Se compara con fuerza bruta sobre todo el índice y con el KD-Tree exacto.

| Escala | Vectores | Fuerza bruta (ms) | KD-Tree (ms) | HNSW (ms) | Recall@10 HNSW | Memoria HNSW | Memoria KD-Tree |
|---|---|---|---|---|---|---|---|
| 1K | 455 | 1,65 ± 0,05 | 1,87 ± 0,06 | 0,80 ± 0,04 | 0,85 | 0,39 MiB | 0,14 MiB |
| 10K | 3.471 | 13,54 ± 0,53 | 7,13 ± 0,34 | 0,87 ± 0,06 | 0,68 | 2,97 MiB | 1,10 MiB |
| 100K | 18.008 | 76,89 ± 2,65 | 21,91 ± 0,88 | 1,03 ± 0,08 | 0,63 | 15,1 MiB | 5,6 MiB |

La desviación reportada es el ruido al repetir la misma consulta (media de las desviaciones por consulta). La diferencia entre consultas se reporta aparte y domina en el KD-Tree (6,5 ms en 100K), cuya poda depende de la posición del punto consultado.

El barrido de ef de búsqueda (16, 32, 64, 128) mostró que en 1K el recall@10 sube de 0,84 a 1,0 al aumentar ef, pero desde 10K se mantiene fijo (0,42 en 10K y 0,51 en 100K) aunque ef se multiplique por ocho. La limitación está en la calidad del grafo construido (M = 8, ef de construcción 48), no en la búsqueda: se requiere evaluar M y ef de construcción mayores. Como implementaciones de referencia se consideran datasketch para MinHash/LSH y hnswlib para HNSW; no se utilizaron en estas corridas.

6. Grafo de co-compra, influencia y comunidades

Se forma un grafo no dirigido y ponderado: cada producto comprado es un nodo y cada par dentro de una orden aceptada incrementa el peso de su arista. PageRank, Louvain y Label Propagation se calculan sobre el mismo subgrafo sin productos aislados.

| Escala | Productos | Con co-compra | Pares (E) | PageRank (ms) | Louvain (ms) | Label Propagation (ms) |
|---|---|---|---|---|---|---|
| 1K | 38 | 32 | 38 | 1,17 ± 0,01 | 0,30 ± 0,01 | 0,10 ± 0,00 |
| 10K | 267 | 211 | 317 | 12,27 ± 0,18 | 2,41 ± 0,03 | 1,17 ± 0,04 |
| 100K | 1.902 | 1.381 | 3.235 | 167,26 ± 4,14 | 29,56 ± 1,31 | 16,56 ± 2,29 |

PageRank ponderado

Se aplica iteración de potencia con amortiguación 0,85, tolerancia 10⁻¹⁰ y un máximo de 100 iteraciones; el coste esperado es O(I(V + E)). Los tiempos resumen 100 repeticiones. Se contrastó cualitativamente su Top-10 con el grado ponderado, una referencia simple de actividad local.

Louvain frente a Label Propagation

Louvain optimiza la modularidad mediante movimientos locales y agregación de comunidades. Label Propagation asigna a cada nodo la etiqueta de mayor peso entre sus vecinos, en orden aleatorio, hasta que ninguna cambia; cuesta O(V + E) por pasada y no optimiza la modularidad de forma explícita. La estabilidad se midió con 10 semillas por algoritmo, comparando las particiones por pares con información mutua normalizada (NMI) y el índice de Rand ajustado (ARI); 1 indica la misma agrupación.

| Escala | Algoritmo | Comunidades | Modularidad | Mayor / mediana | NMI entre semillas (media / mín.) | ARI entre semillas (media / mín.) |
|---|---|---|---|---|---|---|
| 1K | Louvain | 9 | 0,816 | 7 / 3 | 1,000 / 1,000 | 1,000 / 1,000 |
| 1K | Label Propagation | 10 | 0,784 | 5 / 3 | 0,977 / 0,966 | 0,922 / 0,857 |
| 10K | Louvain | 29 | 0,859 | 44 / 4 | 0,975 / 0,948 | 0,890 / 0,762 |
| 10K | Label Propagation | 52 | 0,746 | 22 / 3 | 0,928 / 0,899 | 0,639 / 0,478 |
| 100K | Louvain | 74 | 0,793 | 379 / 2 | 0,984 / 0,974 | 0,970 / 0,945 |
| 100K | Label Propagation | 139 | 0,758 | 397 / 2 | 0,920 / 0,899 | 0,879 / 0,841 |

Louvain obtuvo mayor modularidad y particiones más estables en las tres escalas. Label Propagation fue unas dos veces más rápido pero fragmentó el grafo en más comunidades pequeñas, y su variación entre semillas fue mayor (ARI mínimo 0,48 en 10K). El acuerdo entre ambos algoritmos con la semilla base fue NMI 0,966 / 0,860 / 0,859. Para el servicio de cross-selling se mantiene Louvain; Label Propagation queda disponible en `GET /cocompra/comunidades?metodo=label_propagation`.

7. Protocolo y población observada

Se prepararon perfiles de 1K, 10K, 100K, 1M y 10M eventos con semilla 2026. La campaña reportada se ejecutó en una sola máquina: Windows 10 (10.0.19045), AMD Ryzen 9 5900HS (16 núcleos lógicos), 16 GB de RAM y CPython 3.14.2. Se usó PYTHONHASHSEED = 2026 para que el orden de los conjuntos sea reproducible.

- Consultas de similitud: 10 consultas distintas × 100 repeticiones = 1.000 observaciones por método y escala, sobre índices fijos y con orden de métodos aleatorizado. Se reporta media, desviación por repetición y desviación entre consultas.
- Barrido de parámetros: las mismas 10 consultas × 100 repeticiones por configuración.
- PageRank, Louvain y Label Propagation: 100 repeticiones sobre la misma instantánea; estabilidad con 10 semillas.
- Estructuras base y probabilísticas: tres construcciones completas por caso y 100 repeticiones de un lote fijo de operaciones (1.000 consultas o 5 consultas de KNN), cada caso en un proceso nuevo con la entrada cargada antes de cronometrar.
- Memoria: memoria Python incremental del índice con tracemalloc (actual y pico), tres procesos por caso, excluyendo los datos de entrada.

| Escala | Eventos | Aceptados | Vectores / conjuntos | Productos en el grafo | Con co-compra | Pares |
|---|---|---|---|---|---|---|
| 1K | 1.000 | 998 | 455 | 38 | 32 | 38 |
| 10K | 10.000 | 9.989 | 3.471 | 267 | 211 | 317 |
| 100K | 100.000 | 99.899 | 18.008 | 1.902 | 1.381 | 3.235 |

Las escalas de 1M y 10M están generadas, pero su campaña no se completó en esta máquina dentro del plazo de entrega: la reproducción de 1M eventos por la API se interrumpió y la de 10M, estimada en varias horas, no se inició. Ambas se pueden completar con el script reanudable scripts/campana_final.sh. Una corrida preliminar anterior en otra plataforma (macOS, 25 observaciones por consulta y una ejecución del grafo) alcanzó 10M eventos, con 115.213 vectores, un grafo de 21.066 productos y 156.869 pares, y Louvain con 766 comunidades y modularidad 0,789. Esos valores no se mezclan con las tablas de esta campaña porque provienen de otra plataforma y de otro protocolo.

8. Tiempos, calidad y escalabilidad

Las figuras `docs/informe_figuras/tiempos_construccion.png` y `tiempos_operacion.png` muestran en escala log-log el tiempo de construcción y por operación de las 19 estructuras medidas frente a su carga real. Las pendientes de la sección 3 resumen esas curvas. Las figuras `escalabilidad_consulta.pdf` y `escalabilidad_memoria.pdf` muestran la consulta de similitud y la memoria frente al número de elementos del índice.

| Construcción (ms) | 1K | 10K | 100K |
|---|---|---|---|
| Merge sort (n eventos) | 1,4 | 25,8 | 268,5 |
| Tabla hash (n eventos) | 2,1 | 18,1 | 295,1 |
| B+Tree (n productos) | 0,7 | 14,5 | 50,3 |
| KD-Tree (n vectores) | 6,2 | 64,2 | 296,8 |
| HNSW (n vectores) | 390 | 3.404 | 18.660 |
| MinHash/LSH (n conjuntos) | 31,9 | 267,6 | 2.054,6 |
| Bloom (n claves) | 0,2 | 1,2 | 10,3 |
| CMS (n actualizaciones) | 0,3 | 2,0 | 17,8 |

En 100K, la fuerza bruta vectorial tardó 76,9 ms frente a 1,03 ms de HNSW, con recall@10 de 0,63; Jaccard exhaustivo tardó 36,9 ms frente a 0,04 ms de MinHash/LSH, con recall@10 de 0,16 en la configuración por defecto y 0,61 con 32 × 2. La mejora de latencia no implica calidad suficiente: la configuración debe elegirse sobre la curva de calidad frente a latencia (`docs/informe_figuras/barrido_similitud_100K.png`). HNSW es además la construcción más cara (18,7 s en 100K), un coste que se paga una vez por reconstrucción.

9. Memoria actual y pico

Se informa la memoria Python incremental de cada índice, excluyendo las entradas compartidas. Se midieron tres procesos por caso; los picos incluyen temporales de construcción. Las comparaciones de la misma familia recibieron idéntica carga.

| Índice (100K) | Carga | Actual (MiB) | Pico de construcción (MiB) |
|---|---|---|---|
| Bloom | 2.175 claves | 0,003 | 0,004 |
| Conjunto exacto | 2.175 claves | 0,125 | 0,157 |
| CMS | 6.132 actualizaciones | 0,032 | 0,033 |
| Conteo exacto | 6.132 actualizaciones | 0,056 | 0,083 |
| HNSW | 18.008 vectores | 15,136 | 15,167 |
| KD-Tree | 18.008 vectores | 5,609 | 9,554 |
| Mapa vectorial (fuerza bruta) | 18.008 vectores | 0,396 | 0,396 |
| MinHash/LSH | 18.008 conjuntos | 113,367 | 113,372 |
| Mapa de conjuntos (exhaustivo) | 18.008 conjuntos | 0,396 | 0,396 |

Bloom y CMS ocupan menos memoria que sus referencias exactas; la diferencia de Bloom crece con el número de claves. HNSW y MinHash/LSH requieren considerablemente más memoria que los mapas exactos: es el precio de responder en tiempo casi constante. LSH guarda 64 valores de firma por conjunto más 16 tablas de cubetas, lo que explica sus 113 MiB.

10. Evaluación de requisitos y conclusiones

| Requisito | Estado observado |
|---|---|
| Pipeline de punta a punta | Una orden recorre las diez etapas por la API (FIFO, lote, servicios) con una salida observable por etapa. |
| Escalas de eventos | 1K, 10K y 100K medidos; 1M y 10M generados pero no medidos en esta campaña. |
| 100 repeticiones, media, desviación, plataforma y semilla | Cumplido en consultas, grafo y operaciones; construcciones con tres repeticiones por coste. |
| Escalabilidad log-log y contraste con la complejidad | Construcción y operación de 19 estructuras, con pendientes ajustadas frente a las esperadas. |
| Bloom y CMS frente a exacto | Tiempo, memoria, FP observada frente a teórica y error de CMS frente a la cota ε·N. |
| Conjuntos y ANN frente a exacto | Tiempo, recall@5 y recall@10 y memoria, con barrido de parámetros. |
| Comunidades | Louvain frente a Label Propagation: modularidad, tiempo, número y tamaños, y estabilidad con NMI y ARI. |
| Memoria actual y pico | tracemalloc en tres procesos por caso. |

Las estructuras aproximadas cumplieron su promesa de latencia con costes distintos en cada familia. Bloom y CMS ahorran memoria con un error controlado y verificable, aunque en Python son más lentos por consulta que las estructuras exactas nativas. HNSW mantiene la consulta cerca de 1 ms al crecer el índice, pero su recall depende de la construcción del grafo más que de ef de búsqueda. MinHash/LSH es el más rápido y el más costoso en memoria, y su configuración debe ajustarse al nivel de similitud del dominio: 32 × 2 supera ampliamente a la configuración inicial. Louvain resultó preferible a Label Propagation por calidad y estabilidad. Quedan pendientes medir 1M y 10M con el mismo protocolo, explorar M y ef de construcción de HNSW, y llevar el B+Tree a disco.

Referencias fundamentales

- Bloom (1970), Space/time trade-offs in hash coding with allowable errors.
- Cormode y Muthukrishnan (2005), An improved data stream summary: The Count-Min sketch and its applications.
- Broder (1997), On the resemblance and containment of documents; Indyk y Motwani (1998), Approximate nearest neighbors.
- Malkov y Yashunin (2020), Efficient and robust approximate nearest neighbor search using hierarchical navigable small world graphs.
- Bentley (1975), Multidimensional binary search trees used for associative searching.
- Bayer y McCreight (1972), Organization and maintenance of large ordered indexes; Comer (1979), The ubiquitous B-tree.
- Brin y Page (1998), The anatomy of a large-scale hypertextual Web search engine.
- Blondel et al. (2008), Fast unfolding of communities in large networks; Raghavan et al. (2007), Near linear time algorithm to detect community structures in large-scale networks.
- Hubert y Arabie (1985), Comparing partitions; Strehl y Ghosh (2002), Cluster ensembles: a knowledge reuse framework for combining multiple partitions.
