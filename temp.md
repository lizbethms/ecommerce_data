1. Investigación y Documentación (30% — 6 puntos, grupal)
Para las etapas 0–5 se requiere una documentación breve de la función en el pipeline, complejidad y justificación
frente a alternativas. Para las etapas 6–8 se exige documentación profunda de las cinco familias de algoritmos,
incluido paper original, implementaciones de referencia y benchmarks.
Informe: PDF de 8–12 páginas con resumen, contexto, arquitectura, investigación, diseño, resultados,
conclusiones y referencias.
2. Implementación del Sistema (20% — 4 puntos, grupal)
El pipeline debe ejecutarse de punta a punta: un evento debe atravesar las diez etapas y producir una salida
observable, como recomendación, alerta, ranking o resultado Top-K. La demo debe mostrar prioridades, filtrado
probabilístico, similitud frente a un método exacto, análisis del grafo y servicio al usuario final.
3. Experimentación y Análisis (20% — 4 puntos, grupal)
Incluir los resultados experimentales en el informe:
● Generar datasets de 1K, 10K, 100K, 1M y 10M elementos para etapas [FIJA] y estructuras base reportadas.
● Medir tiempos con 100 repeticiones cuando sea viable; reportar promedio, desviación estándar,
plataforma y semilla. Para 10M, justificar menos repeticiones si existen restricciones.
● Graficar escalabilidad log-log y contrastar las complejidades esperadas.
● Comparar estructuras probabilísticas con una alternativa exacta: tiempo, memoria, falsos positivos y error
de frecuencia.
● Comparar la técnica de conjuntos con fuerza bruta y la técnica ANN con KNN exacto/fuerza bruta, usando
tiempo, recall@K y memoria.
● Comparar comunidades en el mismo grafo: modularidad, tiempo, número y tamaños de comunidades, y
estabilidad.
● Medir memoria actual y pico con tracemalloc u otra herramienta equivalente.
4. Presentación y Sustentación (30% — 6 puntos, nota individual)
Presentación: 15 minutos de exposición más 10 de preguntas, 10–15 diapositivas y demo de 3–4 minutos. El
bloque de preguntas se dirige a cada integrante por separado.
Este componente no se promedia con el grupo: cada estudiante recibe su propia nota sobre 6 puntos, de acuerdo
con el siguiente desglose.
Criterio individual Descripción Pts.
Exposición de su
parte
Claridad al presentar la etapa o familia de algoritmos de la que fue responsable,
manejo del tiempo y calidad de las diapositivas y de la demo que expone. 2
Sustentación oral
Responde de dos a tres preguntas sobre cualquier parte del proyecto, no solo sobre
la que desarrolló. Se evalúa si justifica las decisiones de diseño, la elección de
estructuras y el significado de los resultados experimentales.
3
Contribución técnica
verificable
Historial de contribuciones en el repositorio, responsabilidad declarada sobre al
menos una etapa del pipeline y coherencia entre lo declarado y lo sustentado. 1
Reglas de aplicación
● Cada integrante debe ser responsable principal de al menos dos etapas del pipeline o de una familia de
algoritmos del bloque avanzado, y debe exponer esa parte en la presentación.
● Las preguntas pueden ser sobre cualquier etapa del pipeline.
● Si un integrante no puede explicar el algoritmo o el resultado que él mismo presenta, obtiene 0 en la
sustentación.
● La inasistencia a la exposición sin justificación implica 0 en los 6 puntos de este componente.
● La nota final de cada estudiante es la suma de los 14 puntos grupales y sus 6 puntos individuales.
Entregables
1. Repositorio de GitHub con código fuente, README, informe PDF, notebooks y diagrama del pipeline.
2. Informe PDF de 8–12 páginas: Proyecto_Final_[NombreGrupo].pdf; subir al campus virtual e incluir en el
repositorio.
3. Presentación final obligatoria en la penúltima semana de clases.
4. Tabla de roles y contribución individual en el README: responsable principal de cada etapa del pipeline y
aporte concreto de cada integrante, consistente con el historial del repositorio.
