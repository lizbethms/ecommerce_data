# Contrato y decisiones de la etapa 0

## Flujo implementado

```text
10M.csv (solo lectura)
  → validación y enriquecimiento incremental
  → SQLite temporal/de entidades + escenarios controlados
  → events.jsonl ordenado por (event_time, secuencia estable) + manifiesto
  → lector por bloques en thread → reloj asyncio → FIFO acotada
  → sumidero de sobres JSONL (entrada de la futura etapa 1)
```

La preparación inicial valida lo necesario para construir datos coherentes; no implementa la etapa 1 de ordenación y deduplicación de lotes. El sumidero deja pasar los reenvíos para que su tratamiento se implemente en las etapas correspondientes. Los estados derivados de preparación contabilizan cada compra original una vez.

## Reglas de datos

1. **Fuente:** se abre únicamente en lectura. La preparación escribe en un directorio nuevo. Cada manifiesto registra el SHA-256 completo de la fuente; calcularlo requiere leer todo el CSV incluso para preparar 1K.
2. **Dinero y fechas:** precios decimales serializados como texto de dos decimales; las operaciones de validación usan `Decimal`. Fechas UTC. IDs originales como cadenas, sin convertirlos en coordenadas ni números de punto flotante.
3. **Faltantes:** marcas y códigos desconocidos son `null`. Se conserva `category_id`. No se imputan atributos usando datos posteriores. Cada sesión ausente recibe una sesión sintética exclusiva de esa fila, con procedencia registrada.
4. **Precios cero:** se conservan con `zero_price_review`; no se infiere que representen promociones ni errores.
5. **Identidad:** el hash de fuente completa y el número de registro forman la identidad real estable entre tamaños. Dos filas iguales reciben IDs distintos y una marca de posible duplicado. Un reenvío inyectado mantiene identidad, tiempo y contenido de negocio; cambia únicamente su etiqueta de evaluación.
6. **Órdenes reales derivadas:** compras del mismo usuario y sesión se agrupan en buckets UTC fijos de 30 minutos, configurables. No se usan ventanas deslizantes: 00:29 y 00:30 pertenecen a buckets diferentes. Cantidad supuesta de una unidad y entrega estándar. Los campos añadidos se declaran en `synthetic_fields`. No se inventan pagos observados para esas compras.
7. **Cortes:** el prefijo seleccionado puede cortar sesiones u órdenes; el manifiesto lo advierte y señala la última fila. Las órdenes derivadas solo cubren el prefijo seleccionado. Los escenarios reservados están completos y sus referencias quedan dentro del dataset. No se afirma que una orden derivada sea una orden real completa.
8. **Catálogo:** cada evento conserva sus atributos observados; el catálogo guarda la última observación del prefijo por producto, incluyendo `null`. Los cambios generan una marca; no se confunde la última observación con el precio actual. No se completan eventos pasados con el catálogo final.
9. **Inventario:** es enteramente sintético. Inicia en cero y recibe la reposición mínima necesaria antes de cada compra única. Una devolución repone stock. La tabla registra unidades suministradas, compradas y devueltas; verifica `stock = supplied − purchased + returned ≥ 0`. Las reposiciones están agregadas en la entidad de inventario, no son eventos adicionales del stream. No permite evaluar faltantes de stock reales.
10. **Ciclo sintético:** para tres órdenes se generan pagos anteriores a las compras, entregas express/estándar/programada y una orden express con dos productos distintos. La devolución referencia una compra anterior del mismo usuario, producto y orden y no supera sus unidades. La entrega programada ocurre tres días después del inicio del escenario.
11. **Evaluación y prioridad:** los dos fallos de pago son casos etiquetados de estrés, no fraude acreditado. Prioridad 100 por estado de pago fallido, 10 por express y 0 por defecto. La FIFO mantiene orden de llegada; aún no hay heap ni reordenamiento por prioridad.

Los 13 eventos reservados son cinco intentos de pago, cuatro compras, una devolución, una reseña, una búsqueda y un reenvío de compra. Se añaden después del último evento real seleccionado, salvo el reenvío, que conserva la fecha de su compra y se ordena junto a ella. Los productos provienen del catálogo del prefijo; usuario, sesión, orden y medios de pago controlados usan el espacio `syn:`. La semilla determina las cantidades de compra. Cambiar configuración o tamaño cambia la identidad de la corrida sintética; las identidades reales permanecen estables.

## Concurrencia, errores y escalabilidad

`asyncio.Queue(maxsize=capacidad)` ofrece inserción/extracción O(1), espera asíncrona al llenarse y orden FIFO. Es adecuada para desacoplar productor y consumidor con un límite explícito; una lista requeriría desplazamientos para extraer al frente y una deque por sí sola no implementaría espera asíncrona. La capacidad debe ser positiva: no se permite una cola ilimitada.

La lectura y escritura de bloques se ejecutan con `asyncio.to_thread`; la coordinación y el pacing viven en el event loop. No se introducen cálculos intensivos de similitud ni grafo. `TaskGroup` propaga errores y cancela la otra tarea para evitar esperas indefinidas. La finalización normal usa un centinela y vacía el último bloque. Una ejecución fallida puede dejar archivos parciales; la ausencia de manifiesto o métricas finales indica que no terminó. Se debe elegir una salida nueva al reintentar.

La memoria residente de la etapa 0 es O(capacidad FIFO + tamaño de bloque), además de buffers de serialización. El throughput depende del pacing y del sumidero. La preparación utiliza índices SQLite en disco, caché de 8 MiB y ordenación temporal con almacenamiento temporal en disco: costo aproximado O(N log N), almacenamiento O(N), memoria independiente de N. Se conservan tanto JSONL como SQLite para trazabilidad, con costo adicional de disco. Para 10M aún no se ha medido tiempo ni espacio requerido.

Esta entrega comprueba trazabilidad, integridad de referencias, identidad de reenvíos y balances. Los timestamps de ingesta y las métricas varían entre reproducciones; los eventos preparados son reproducibles. No hay detección de fraude, deduplicación online, confirmación de índices ni resultados de recomendación; esas funciones pertenecen a etapas posteriores.
