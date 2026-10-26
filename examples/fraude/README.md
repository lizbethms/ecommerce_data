# Pruebas de `/fraude`

Desde la raíz del proyecto, instala las dependencias y arranca un servidor local con **un historial nuevo**:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
FRAUDE_HISTORIAL=data/fraude/ejemplo_http_01.csv .venv/bin/uvicorn src.api.fraud:create_app --factory --workers 1 --host 127.0.0.1
```

La documentación interactiva está en http://127.0.0.1:8000/docs. Para otro recorrido independiente cambia el nombre del historial; los archivos existentes se recuperan, no se vacían.

## Recorrido completo y reproducible

En otra terminal:

```sh
.venv/bin/python examples/fraude/probar_api.py
```

El script carga las tres entidades de `entidades.csv`, envía los 28 eventos en orden y compara todas las respuestas con `resultados_esperados.json`. Incluye pago normal, entidad señalada, 24 intentos de otro dispositivo, reenvío del primer intento y expiración seis minutos después. El intento 20 activa la revisión por frecuencia; el reenvío conserva la señal original y no cuenta otra vez. El intento posterior a la expiración estima 1.

Después del recorrido, estos ejemplos comprueban errores:

```sh
curl -i -H 'Content-Type: application/json' --data-binary @examples/fraude/pago_invalido.json http://127.0.0.1:8000/fraude/eventos
curl -i -H 'Content-Type: application/json' --data-binary @examples/fraude/pago_conflictivo.json http://127.0.0.1:8000/fraude/eventos
```

Se esperan HTTP 422 y 409, respectivamente. Detén y vuelve a iniciar el servidor con el mismo historial para probar recuperación. Reenviar `pago_normal.json` devolverá `duplicado` y su resultado original.

## Prueba manual con curl

Para este recorrido usa **otro historial nuevo**. Registra primero el dispositivo:

```sh
curl -X PUT -H 'Content-Type: application/json' -d '{"motivo":"Caso ficticio de prueba"}' http://127.0.0.1:8000/fraude/entidades/dispositivo/syn:example:flagged
curl -H 'Content-Type: application/json' --data-binary @examples/fraude/pago_normal.json http://127.0.0.1:8000/fraude/eventos
curl -H 'Content-Type: application/json' --data-binary @examples/fraude/pago_entidad_senalada.json http://127.0.0.1:8000/fraude/eventos
curl http://127.0.0.1:8000/fraude/metricas
curl http://127.0.0.1:8000/fraude/entidades
curl -X DELETE http://127.0.0.1:8000/fraude/entidades/dispositivo/syn:example:flagged
```

Las dos decisiones iniciales serán `continuar` y `revisar`. Retirar una entidad afecta eventos futuros; los reenvíos devuelven el resultado original.

## Recorrido por lotes

```sh
.venv/bin/python scripts/stage6.py --events examples/fraude/eventos.jsonl --entities examples/fraude/entidades.csv --history data/fraude/ejemplo_lote_01.csv --output results/ejemplo_lote_01.jsonl --metrics results/ejemplo_lote_01_metrics.json
```

La salida contiene sobres con `stage_results["6"].risk_signals`. La API traduce sus nombres al español. Si la entrada ya contiene sobres de etapa 0, preserva sus resultados y tiempos.

Los datos son ficticios, con fechas UTC fijas; no se necesita `10M.csv`. Las colisiones de Bloom y CMS se fuerzan de manera determinista en `tests/test_stage6.py`.
