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
Se analizó un sistema de procesamiento de eventos de comercio electrónico con cinco escalas, desde 1.000 hasta 10.000.000 de eventos. En la escala mayor se aceptaron 9.989.999 eventos, se construyeron 115.213 vectores y conjuntos, y se obtuvo un grafo de 21.066 productos y 156.869 pares de co-compra. Se compararon consultas aproximadas con referencias exhaustivas y se midió memoria incremental de índices en tres procesos por escala.
Se observó una reducción marcada de latencia en HNSW y MinHash/LSH, acompañada de mayor memoria y de pérdidas de recall. Se completó la serie de cinco tamaños de eventos; las consultas se midieron sobre índices fijos con 25 observaciones y cinco consultas distintas. 

1. Contexto y objetivo
Se eligió el escenario de comercio electrónico para integrar ingesta, prioridades, búsqueda, detección de actividad sospechosa, similitud y análisis de co-compra. Se parte de eventos reales enriquecidos con un componente sintético que incorpora pagos, órdenes y casos controlados. Se busca que la salida de una etapa alimente funciones posteriores y produzca resultados observables en el servicio.
La unidad principal de escala es el evento procesado. El número de claves de pago, vectores, conjuntos y nodos del grafo se informa por separado; no se interpreta que 10M eventos equivalgan a 10M elementos en cada índice.

2. Arquitectura del pipeline
Etapa
Estructura
Función
0
FIFO acotada
Recibe eventos y controla ocupación.
1
Ordenación y búsqueda binaria
Prepara lotes y facilita deduplicación.
2
Heap
Ordena alertas y órdenes por urgencia.
3
Hash, matriz dispersa y LRU
Mantiene estado, interacciones y caché.
4
B+Tree
Resuelve búsquedas puntuales y rangos.
5
KD-Tree
Proporciona KNN exacto para comparación.
6
Bloom y CMS
Filtra claves y estima frecuencias de pago.
7
MinHash/LSH y HNSW
Propone vecinos de conjuntos y vectores.
8
PageRank y Louvain
Calcula influencia y comunidades de co-compra.
9
Trie, Top-K, API y panel
Entrega autocompletado, recomendaciones y métricas.


Se observan salidas de búsqueda, recomendaciones, alertas y comunidades en el servicio. El flujo de reproducción de la FIFO y el recorrido HTTP de la demostración se ejecutan por rutas distintas. Por ello, todavía no se demuestra que un único evento atraviese las diez etapas en una sola ruta integrada.
El B+Tree implementado reside en memoria. Su comportamiento no permite atribuir rendimiento de disco ni satisfacer por completo la exigencia específica de un índice de disco. La fuerza bruta se utiliza para verificar la línea base exacta de similitud; el cálculo de recall se realiza fuera del intervalo de consulta aproximada.

3. Estructuras base: función, coste y elección
Estructura
Coste esperado
Justificación
FIFO
Operación O(1); memoria O(C)
Se conserva el orden y se limita la ocupación.
Merge sort + binaria
O(B log B) y O(log B)
Se favorecen búsquedas repetidas sobre lotes ordenados frente a barridos lineales.
Heap
Inserción y extracción O(log N)
Se actualizan prioridades sin reordenar toda la lista.
Hash table
O(1) esperado; O(N) peor caso
Se acelera el lookup sujeto a carga y colisiones.
Matriz dispersa
O(nnz) memoria
Se almacenan sólo interacciones observadas.
LRU
O(1) esperado; O(C) memoria
Se aprovecha localidad con capacidad fija.
B+Tree
O(log_m N) más salida de rango
Se sostienen rangos ordenados frente al hash; la variante actual es en memoria.
KD-Tree
Construcción actual O(N log² N)
Se ofrece KNN exacto; la consulta puede degradarse.
Trie y Top-K
O(L) más salida; O(N log K)
Se atienden prefijos y rankings parciales sin ordenar todo.


4. Filtrado probabilístico
Bloom Filter
Se representa la pertenencia con bits y varias funciones hash. Se obtienen inserción y consulta O(k), con memoria que crece con la capacidad configurada. Un negativo es concluyente mientras no se eliminen bits; un positivo se verifica contra un registro exacto antes de adoptar una decisión crítica. Se eligió por ahorro de memoria frente a un conjunto exacto, a cambio de falsos positivos y una verificación adicional.
En 10M se insertaron 215.114 claves únicas. Se registraron 0,2463 MiB de memoria actual en Bloom y 8,0002 MiB en el conjunto exacto. En el control de 10.000 consultas ausentes se observaron cero falsos positivos y cero falsos negativos. Esta observación no equivale a una tasa global nula.

Count-Min Sketch
Se actualizan “d” contadores y se estima una frecuencia con el mínimo de las filas. Para incrementos no negativos, las colisiones pueden sobreestimar el conteo del mismo universo. Se emplean cuatro filas y ancho 1.024 en la campaña de memoria. En la variante temporal se usan seis bloques de 100 segundos para una ventana nominal de 600 segundos. Los bordes de bloque pueden diferir de una ventana deslizante exacta.
En 10M se midieron 615.777 actualizaciones de pago. La memoria actual fue 0,1570 MiB para CMS y 7,3410 MiB para el conteo exacto. En un caso controlado se obtuvieron estimaciones 1–6 iguales al exacto. No se dispone todavía de MAE, RMSE ni error máximo sobre una carga representativa con colisiones.
Se consideran pybloomfiltermmap3 y Apache DataSketches como implementaciones de referencia para Bloom y CMS. En las mediciones se utilizó la implementación del proyecto y se contrastó con estructuras exactas de Python.

5. Similitud aproximada
Conjuntos: MinHash y LSH
Se estima Jaccard con 64 permutaciones MinHash y se recuperan candidatos mediante 16 bandas de cuatro filas. La generación de firmas depende de las permutaciones y del tamaño total de conjuntos. La consulta depende de colisiones y candidatos, sin garantía universal de sublinealidad. Se compara con Jaccard exhaustivo sobre todos los conjuntos del mismo índice.
En 10M se indexaron 115.213 conjuntos. Se observaron 0,0330 ± 0,0178 ms por consulta MinHash/LSH frente a 437,90 ± 25,93 ms con Jaccard exhaustivo. El recall@5 fue 0,24. La memoria incremental del índice aproximado alcanzó 862,85 MiB frente a 3,67 MiB del mapa exhaustivo.


Vectores: HNSW y KNN exacto
Se navega un grafo jerárquico de vecinos para proponer candidatos. Se configuraron M=8, ef de construcción 48 y ef de búsqueda 32. Se utilizaron vectores de 19 dimensiones y distancia euclidiana. Se comparó la búsqueda con fuerza bruta sobre todo el índice y con KD-Tree exacto. El coste depende de parámetros y datos; se evita atribuir una cota universal.
Para 115.213 vectores se observaron 0,6285 ± 0,1434 ms con HNSW y recall@5 de 0,72; la fuerza bruta tardó 247,70 ± 22,27 ms y KD-Tree 40,80 ± 4,38 ms. La memoria actual fue 99,12 MiB para HNSW, 37,06 MiB para KD-Tree y 3,67 MiB para el mapa exacto, sin incluir vectores de entrada.
Se tomaron 25 observaciones sobre índices fijos y cinco consultas distintas. La desviación mezcla consultas y repeticiones; no representa reconstrucciones independientes. Se requiere evaluar K=10, más consultas y el efecto de variar ef de búsqueda. Como implementaciones de referencia se consideran datasketch para MinHash/LSH y hnswlib para HNSW; no se utilizaron en estas corridas.

6. Grafo de co-compra, influencia y comunidades
Se forma un grafo no dirigido y ponderado: cada producto comprado es un nodo y cada par dentro de una orden aceptada incrementa el peso de su arista. En 10M se registraron 21.066 productos, 156.869 pares y peso acumulado 374.880. PageRank y Louvain se calcularon sobre 10.140 productos con co-compra; 10.926 aislados quedaron fuera del análisis.

PageRank ponderado
Se aplica iteración de potencia con amortiguación 0,85, tolerancia 10⁻¹⁰ y un máximo de 100 iteraciones. El coste esperado es O(I(V+E)). En 10M se registraron 4.044,09 ms en una ejecución. Se contrastó cualitativamente su Top-10 con el grado ponderado, una referencia simple de actividad local, no una solución exacta de PageRank.

Louvain y comparación pendiente
Se optimiza la modularidad mediante movimientos locales y agregación de comunidades. En 10M se obtuvieron 766 comunidades, modularidad ponderada 0,7888 y tiempo de 565,55 ms en una ejecución. La mayor comunidad contiene 2.451 productos. No se estimó desviación temporal ni estabilidad entre semillas.
Se requiere ejecutar Label Propagation ponderado sobre exactamente el mismo grafo y población para comparar modularidad, tiempo, número y tamaños de comunidades, además de estabilidad de particiones. NetworkX ofrece implementaciones de referencia para ambos métodos; no se utilizaron en la corrida presentada.

Figura 1. Veinte comunidades mayores de Louvain en la escala 10M; la gráfica no representa una comparación entre algoritmos.

7. Protocolo y población observada
Se prepararon cinco perfiles de 1K, 10K, 100K, 1M y 10M eventos, con semilla 2026. La campaña de memoria se ejecutó en macOS 26.7.1 arm64 y Python 3.14.6, con tres procesos nuevos por estructura y escala. Se registraron memoria Python actual y pico de construcción, así como RSS de proceso. Los tiempos de similitud corresponden a 25 observaciones sobre cinco consultas distintas y un índice fijo; los tiempos de grafo corresponden a una ejecución por escala. No se dispone de una medición de límites de tiempo o memoria que justifique reducir a 25 las 100 repeticiones solicitadas para 10M.

Escala
Eventos
Aceptados
Vectores/conj.
V total
V analizado
E
1K
1.000
998
455
38
32
38
10K
10.000
9.989
3.471
267
211
317
100K
100.000
99.899
18.008
1.902
1.381
3.235
1M
1.000.000
998.999
57.622
6.843
3.989
23.094
10M
10.000.000
9.989.999
115.213
21.066
10.140
156.869


Las escalas reflejan volumen de eventos. La cardinalidad del índice vectorial se duplicó aproximadamente de 1M a 10M, mientras que el archivo creció diez veces. La diferencia responde al número de productos distintos presentes en los eventos y evita confundir población del archivo con trabajo real de cada estructura.
Escala
Comunidades
Modularidad
PageRank (ms)
Louvain (ms)
1K
9
0,8158
0,70
0,20
10K
29
0,8594
6,82
1,40
100K
74
0,7930
87,54
16,45
1M
244
0,7795
460,01
54,13
10M
766
0,7888
4.044,09
565,55



8. Tiempos, calidad y escalabilidad
Consulta (ms)
1K
10K
100K
1M
10M
Jaccard exacto
0,302
2,895
22,524
106,990
437,897
MinHash/LSH
0,010
0,021
0,042
0,032
0,033
KNN bruto
0,849
6,175
34,895
115,695
247,699
HNSW
0,413
0,367
0,542
0,470
0,628
KD-Tree
0,999
2,981
11,295
24,817
40,799


Recall@5
1K
10K
100K
1M
10M
MinHash/LSH
0,24
0,64
0,68
0,36
0,24
HNSW
0,88
0,68
0,56
0,88
0,72



Figura 2. Tiempo medio de consulta frente al número real de elementos del índice. Ambos ejes son logarítmicos. Cada punto agrega 25 observaciones sobre cinco consultas.

En 10M, la fuerza bruta vectorial tardó 247,70 ms frente a 0,628 ms de HNSW, pero el recall@5 de HNSW fue 0,72. Para conjuntos, Jaccard exhaustivo tardó 437,90 ms frente a 0,033 ms de MinHash/LSH, con recall@5 de 0,24. Por tanto, la mejora de latencia no implica calidad suficiente. Los cambios de media entre escalas aproximadas no permiten concluir tiempo constante.

9. Memoria actual y pico
Se informa memoria Python incremental del índice, excluyendo entradas compartidas; el RSS incluye el proceso completo y no se atribuye al índice. Se midieron tres procesos por caso. Los picos incluyen temporales de construcción. Las comparaciones de la misma familia recibieron idéntica carga.

Índice 10M
Carga
Actual MiB
Pico MiB
RSS MiB
Bloom
215.114
0,246
0,248
290,1
Conjunto exacto
215.114
8,000
12,000
290,7
CMS
615.777
0,157
0,158
290,6
Conteo exacto
615.777
7,341
11,009
287,5
HNSW
115.213
99,116
99,196
291,8
KD-Tree
115.213
37,061
61,965
336,3
Mapa vectorial
115.213
3,667
3,667
289,9
MinHash/LSH
115.213
862,852
862,855
2.125,7
Mapa de conjuntos
115.213
3,667
3,667
846,9



Figura 3. Memoria Python actual frente a carga real de los índices. Ambos ejes son logarítmicos. Cada punto resume tres procesos.

Se observa que Bloom y CMS ocupan menos memoria incremental que las referencias exactas de pagos en esta carga. HNSW y MinHash/LSH requieren considerablemente más memoria que los mapas exactos empleados para la búsqueda exhaustiva. La memoria de los vectores y conjuntos de entrada se excluyó por igual de esos índices; el RSS muestra el coste del proceso completo. La desviación redondeada a 0,0 MiB no implica igualdad bit a bit.




10. Evaluación de requisitos y conclusiones
Requisito
Estado observado
Cinco escalas de eventos
Se completaron 1K, 10K, 100K, 1M y 10M.
100 repeticiones de tiempos
Se dispone de 25 observaciones sobre índices fijos y cinco consultas; se requiere campaña independiente.
Escalabilidad log-log
Se muestran tiempo de consulta y memoria por carga real; falta construcción y estructuras base.
Bloom y CMS frente a exacto
Se comparó memoria; el control Bloom tuvo 0/10.000 falsos positivos. Faltan tiempos y error CMS representativo.
Conjuntos y ANN
Se compararon latencia, recall@5 y memoria frente a métodos exhaustivos.
Comunidades
Se midió Louvain; faltan Label Propagation y estabilidad entre semillas.
Memoria actual y pico
Se midieron cinco escalas en tres procesos por caso; se distingue índice de RSS.


Se completó la escala de 10M y se confirmó la viabilidad de la reproducción aislada y de la campaña de memoria. En consultas aproximadas se observaron ganancias sustanciales de latencia, a costa de calidad y memoria, especialmente en MinHash/LSH. Se evita recomendar el método solo por rapidez hasta ajustar parámetros y ampliar las consultas de evaluación. La modularidad de Louvain describe una sola partición por escala; no constituye evidencia comparativa ni de estabilidad.
Se requiere completar tiempos de construcción y operaciones de estructuras base, cien repeticiones independientes cuando sean viables o justificación cuantificada de una reducción, error de CMS sobre datos representativos, evaluación principal con K=10 y comparación de comunidades sobre la misma instantánea.












Referencias fundamentales
• Bloom (1970), Space/time trade-offs in hash coding with allowable errors.
• Cormode y Muthukrishnan (2005), An improved data stream summary: The Count-Min sketch and its applications.
• Broder (1997), On the resemblance and containment of documents; Indyk y Motwani (1998), Approximate nearest neighbors.
• Malkov y Yashunin (2020), Efficient and robust approximate nearest neighbor search using hierarchical navigable small world graphs.
• Brin y Page (1998), The anatomy of a large-scale hypertextual Web search engine.
• Blondel et al. (2008), Fast unfolding of communities in large networks; Raghavan et al. (2007), Near linear time algorithm to detect community structures.
