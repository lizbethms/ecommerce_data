# Etapa 6: API y servicio de fraude

Implementación local con Python >= 3.11. Produce señales de revisión verificadas sobre datos ficticios; no aplica bloqueos. Las etapas 1–5 y 7–9 siguen pendientes.

## Arquitectura y contratos

```text
HTTP /fraude → adaptador FastAPI ┐
                               ├→ FraudService → Bloom + registro exacto
JSONL → adaptador por lotes     ┘               → 5 CMS + 5 contadores exactos
                                               → historial CSV durable
```

Las estructuras están en `src/structures/probabilistic.py`, el servicio en `src/service/fraud.py` y HTTP en `src/api/fraud.py`. `src/pipeline/stage6.py` procesa una línea a la vez y preserva los sobres previos. El servicio retiene identidades y resultados durante toda la ejecución para asegurar idempotencia: su memoria total crece con el historial, aunque los conteos de frecuencia expiren.

| Método y ruta | Entrada / salida |
|---|---|
| `POST /fraude/eventos` | `{"evento": {...}}`; `evento_id`, `estado`, `senales_riesgo` |
| `PUT /fraude/entidades/{tipo}/{identificador}` | `{"motivo":"Caso sintético"}`; entidad actualizada |
| `DELETE /fraude/entidades/{tipo}/{identificador}` | Retira entidad; operación idempotente |
| `GET /fraude/entidades` | Lista de `tipo`, `identificador`, `motivo` |
| `GET /fraude/metricas` | Configuración, contadores, reloj y ocupación Bloom |
| `GET /fraude/salud` | Disponibilidad y recuperación del historial |

Tipos públicos: `cuenta`, `dispositivo`, `medio_pago`. Se traducen a claves internas `account:`, `device:` y `payment:`. Los campos de eventos conservan sus nombres (`event_id`, `event_time`, etc.). La documentación OpenAPI está en `/docs` y `/openapi.json`.

Estados: `procesado`, `duplicado`, `no_aplica` y `fuera_de_ventana`. Decisiones: `continuar` y `revisar`. `senales_riesgo` contiene:

- `pertenencias`: clave, resultado Bloom, confirmación exacta y falso positivo.
- `frecuencia`: dispositivo, inicio inclusivo y fin exclusivo UTC, estimación, conteo exacto si existe candidato, confirmación y si se contabilizó.
- `decision` y `motivos`: `entidad_senalada` o `alta_frecuencia`.

Un Bloom negativo solo descarta pertenencia al registro insertado. Una estimación CMS elevada requiere confirmación exacta. Las demás comprobaciones continúan aunque una entidad esté señalada. Los eventos ajenos a pagos avanzan el reloj y producen `no_aplica`, sin incrementar frecuencias.

El servicio devuelve `event_id`, `status` y `risk_signals` en inglés. El adaptador por lotes añade esa salida en `stage_results["6"]` y su fecha en `processing_times["6"]`, conservando resultados anteriores. HTTP traduce su respuesta al español.

HTTP 422 indica entrada inválida; 409, identidad con contenido contradictorio; 503, fallo de persistencia. Los errores estructurales de FastAPI conservan su formato estándar.

## Algoritmos, ventanas e identidades

`configs/stage6.json` fija capacidad Bloom 1.000, probabilidad objetivo 0,01, CMS epsilon 0,01 y delta 0,001, y umbral 20. El CMS tiene ancho `ceil(e/epsilon)` y profundidad `ceil(ln(1/delta))`. SHA-256 con prefijo por fila genera índices estables; los contadores usan enteros Python sin desbordamiento.

El reloj es el máximo minuto UTC de eventos nuevos aceptados. La ventana incluye ese minuto y los cuatro anteriores: no equivale exactamente a los últimos 300 segundos. Cada posición del anillo conserva su minuto absoluto. Saltos temporales eliminan bloques vencidos; eventos tardíos dentro de la ventana actualizan su bloque. Los anteriores no incrementan frecuencias, pero sí consultan pertenencia.

La deduplicación precede al avance del reloj. `event_id` y `payment_attempt_id` son identidades independientes. Un mismo intento con otro `event_id` no cuenta otra vez. Se normaliza la fecha a UTC y se excluyen metadatos de recepción, generación, calidad y evaluación del cotejo. Los demás campos deben coincidir; campos omitidos y explícitamente nulos conservan representaciones diferentes.

Los reenvíos devuelven las señales originales y estado `duplicado`, incluso si la ventana o el registro cambiaron después. Las etiquetas de evaluación no intervienen en el detector.

El registro exacto es la fuente de verdad del Bloom. Al cambiar entidades se reconstruye el filtro; si excede la capacidad, esta se duplica hasta cubrirlas. Se reportan ocupación y claves registradas.

Complejidades: Bloom consulta e inserción O(k), espacio O(m) bits; reconstrucción O(nk). CMS actualización/consulta O(d), espacio O(wd) por bloque. El anillo suma cinco consultas y expira cinco posiciones. Los verificadores exactos requieren memoria proporcional a claves activas; la deduplicación retiene O(E) identidades/resultados y recuperar requiere leer O(H) operaciones.

## Historial CSV y recuperación

Columnas: `version,secuencia,operacion,contenido,sha256`. `contenido` es JSON escapado mediante el escritor CSV. El checksum cubre versión, secuencia, operación y contenido. La primera operación guarda configuración; siguen cambios de entidades y eventos válidos, incluidos reenvíos. Conflictos y entradas inválidas no se agregan.

Cada operación se confirma con `flush` y `fsync` antes de actualizar el estado y responder. Al iniciar se verifican secuencia, checksums y configuración y se reproduce el historial. El archivo permanece bloqueado mediante `flock`; una segunda instancia falla. Las mutaciones se serializan mediante un bloqueo del servicio. Usar **un solo worker** en macOS/Linux.

Una escritura fallida impide nuevas mutaciones. Una operación puede haberse escrito aunque el cliente haya recibido 503: después de recuperar, reenviar su identidad es seguro. Un historial incompleto o corrupto impide iniciar indicando la fila y requiere inspección; no se trunca ni repara automáticamente. Los checksums detectan corrupción accidental, no autentican el historial.

Esta versión local no incluye compactación, autenticación ni despliegue compartido. SQLite se mantiene exclusivamente como artefacto de preparación; el estado del servicio se persiste en CSV.

## Ejecución y datos

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
FRAUDE_HISTORIAL=data/fraude/demo_01.csv .venv/bin/uvicorn src.api.fraud:create_app --factory --workers 1 --host 127.0.0.1
```

`FRAUDE_CONFIG` selecciona otra configuración; recuperar requiere la misma configuración. Ver `examples/fraude/README.md` para los 28 ejemplos HTTP, comandos curl y resultados esperados, independientes del CSV original.

```sh
.venv/bin/python scripts/stage0.py prepare --profile stage6 --size 1000 --output data/prepared/fraude_1K
.venv/bin/python scripts/stage0.py prepare --profile stage6 --size 10000 --output data/prepared/fraude_10K
.venv/bin/python scripts/verify_stage6.py
.venv/bin/python scripts/benchmark_stage6.py --output results/stage6_benchmark_metrics.json
```

Estos nombres ya se usaron en la entrega. Para repetir, generar carpetas nuevas y pasar `--prepared-root`, `--results` y `--history-root` al verificador. El benchmark también requiere una salida nueva.

Cada dataset reserva 39 registros sintéticos: los 13 escenarios de etapa 0 y 26 nuevos (24 pagos únicos, un reenvío y un pago posterior a expiración). El resto es un prefijo real: 961 y 9.961 filas. Se mantienen órdenes coherentes, manifiestos con hashes y un registro inicial `entidades.csv`. La preparación predeterminada sigue siendo `stage0`, con 13 registros reservados.

## Resultados y límites

Pasaron 18 pruebas automatizadas y los 28 ejemplos contra Uvicorn por HTTP real. Se cubren colisiones forzadas, saturación, retiros del registro, umbral, expiración, tardíos, identidades, conflictos, errores HTTP, escritura fallida, recuperación, corrupción y sobres previos.

| Corrida | Eventos | Pagos únicos contabilizados | Reenvíos | Revisiones verificadas | Tiempo total |
|---|---:|---:|---:|---:|---:|
| 1K | 1.000 | 30 | 2 | 10 | 0,114 s |
| 10K | 10.000 | 30 | 2 | 10 | 1,364 s |

En cada corrida hubo cinco revisiones por entidad señalada y cinco por frecuencia. El pago final tuvo estimación 1 después de expirar los anteriores. Se verificaron hashes, recuperación y reenvío tras reinicio. Los tiempos incluyen persistencia, serialización y salida. Las métricas separan tiempo total, procesamiento de eventos y escrituras CSV; el tiempo CSV incluye configuración y carga de entidades.

Los microbenchmarks hicieron 100 repeticiones con estado nuevo para 1.000/10.000 claves Bloom y 1.000/10.000 actualizaciones CMS, con distribución sintética y semilla 2026. Separan construcción, actualización y consulta; miden memoria con `tracemalloc` en otra pasada. Excluyen CSV, HTTP y generación de los tiempos, y excluyen claves preexistentes compartidas de la memoria atribuida. No hubo calentamiento separado. Se registra plataforma, Python y dependencias; la RAM física no pudo consultarse por restricciones del entorno.

| Medida | Escala 1K | Escala 10K |
|---|---:|---:|
| Falsos positivos Bloom / ausentes | 1,00% | 0,82% |
| Falsos negativos Bloom | 0 | 0 |
| Error medio CMS | 0 | 3,753 |
| Error máximo CMS | 0 | 27 |
| Subestimaciones CMS | 0 | 0 |

El diccionario exacto ocupó menos memoria incremental que el CMS en estas entradas. El benchmark mide un CMS individual; el servicio mantiene hasta cinco, verificadores e identidades. No implica ahorro global ni eficacia contra fraude real. Las escalas de claves del microbenchmark difieren de los 31 registros de pago de cada dataset preparado. Las métricas completas están en `results/stage6_*_metrics.json`.
