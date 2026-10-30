# Ecommerce: estructuras de datos y análisis de eventos

Proyecto sobre eventos de ecommerce de REES46: prepara datos reales y sintéticos, reproduce tráfico y ofrece servicios mediante FastAPI y un dashboard Streamlit.

## 1. Instalar y preparar el entorno

Requiere Python 3.11 o superior. Ejecuta los comandos desde la raíz del proyecto:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Coloca el archivo original `10M.csv` en la raíz. En cada terminal nueva, activa el entorno con `source .venv/bin/activate`.

## 2. Generar los datos

Usa los scripts de [scripts/ejemplos/](scripts/ejemplos/). Para seguir esta guía, genera **1K eventos**:

```sh
bash scripts/ejemplos/generar_1K.sh
```

Para otra escala, elige el script correspondiente:

| Eventos | Script |
|---:|---|
| 1.000 | [generar_1K.sh](scripts/ejemplos/generar_1K.sh) |
| 10.000 | [generar_10K.sh](scripts/ejemplos/generar_10K.sh) |
| 100.000 | [generar_100K.sh](scripts/ejemplos/generar_100K.sh) |
| 1.000.000 | [generar_1M.sh](scripts/ejemplos/generar_1M.sh) |
| 10.000.000 | [generar_10M.sh](scripts/ejemplos/generar_10M.sh) |

Los scripts usan [configs/prepare.json](configs/prepare.json). Por defecto, el 20 % de los eventos es sintético; puedes ajustar `synthetic.fraction`, la semilla y otros parámetros por perfil. N incluye los escenarios controlados y los reenvíos.

La salida queda en `data/prepared/perfil_<escala>/`:

- `events.parquet`: eventos para la FIFO, la API y el análisis.
- Otros archivos Parquet y `entities.sqlite`: catálogo, órdenes e inventario, entre otras entidades.
- `manifest.json`: configuración efectiva, conteos, hashes y validaciones.

Si los datos ya están generados, reutiliza su carpeta. Para otra fuente o una nueva corrida:

```sh
bash scripts/ejemplos/generar_1K.sh \
  --source /ruta/datos.csv --output data/prepared/otra_1K
```

Las salidas deben ser nuevas. Si cambias la carpeta, reemplaza `data/prepared/perfil_1K` en los pasos siguientes. Puedes seleccionar otra configuración con `CONFIG=/ruta/config.json` antes de `bash`.

## 3. Medir la FIFO (opcional)

Con el entorno activado:

```sh
python scripts/data_pipeline.py --config configs/replay.json replay \
  --events data/prepared/perfil_1K/events.parquet \
  --output results/flujo_1K/fifo/eventos.jsonl \
  --metrics results/flujo_1K/fifo/metricas.json \
  --mode unlimited
```

Revisa `metricas.json` para ver conteos, throughput, latencia, memoria y ocupación de la cola. Esta ejecución escribe un archivo; **todavía no envía los eventos a la API**.

## 4. Generar el informe (opcional)

```sh
PYTHONHASHSEED=2026 python scripts/demo_tecnica.py \
  --datos data/prepared/perfil_1K \
  --salida results/flujo_1K/informe \
  --semilla 2026 --k 5 --consultas 5 --repeticiones 5
```

Abre `results/flujo_1K/informe/resumen.md`. La misma carpeta contiene `evidencia.json`, tablas y figuras. El análisis usa una aplicación aislada y no requiere levantar la API. También puedes explorar los resultados en el [notebook](notebooks/01_demo_tecnica.ipynb).

El informe incluye un resumen del monitor al terminar esa reproducción: ingesta, eventos aceptados por tipo y origen, alertas de pago, ventas y cola. Las alertas son órdenes señaladas para revisión o bloqueo, no fraudes confirmados. La sección de fraude distingue alertas por orden de decisiones por intento de pago.

## 5. Iniciar la API, el dashboard y el tráfico

Abre **tres terminales** desde la raíz del proyecto. Los tres comandos usan los datos del paso 2.

**Terminal 1 — API:**

```sh
source .venv/bin/activate
ECOMMERCE_DATOS=data/prepared/perfil_1K PRECARGAR=0 \
  python -m uvicorn API_SERVICIOS.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — dashboard:**

```sh
source .venv/bin/activate
ECOMMERCE_API_URL=http://127.0.0.1:8000 \
  python -m streamlit run dashboard/app.py --server.port 8501
```

**Terminal 3 — enviar eventos:**

Cuando la API esté lista y tengas abierto el dashboard, ejecuta:

```sh
source .venv/bin/activate
python -m API_SERVICIOS.cliente_trafico \
  --eventos data/prepared/perfil_1K/events.parquet \
  --url http://127.0.0.1:8000 \
  --lote 20 --tasa 100 --reenvios 0 --invalidos 0
```

| Interfaz | Dirección |
|---|---|
| Dashboard: ingesta, ventas, cola y fraude | <http://localhost:8501> |
| Swagger: consultar y probar los servicios | <http://127.0.0.1:8000/docs> |
| Estado de la API | <http://127.0.0.1:8000/salud> |

El dashboard consulta la API periódicamente; el cliente es quien envía el tráfico. El archivo ya puede contener duplicados, por lo que los eventos aceptados pueden ser menos que N. Para repetir desde cero, detén la API con `Ctrl+C`, vuelve a iniciarla y ejecuta otra vez el cliente. Mantén `PRECARGAR=0` en este flujo para enviar el archivo una sola vez.

Para comparar el dashboard con el informe, usa el **mismo** `events.parquet` y espera a que termine el cliente. Comprueba la carpeta indicada en el dashboard, los eventos aceptados, duplicados y rechazados, y luego las alertas y ventas. El informe es una captura de una API aislada; el dashboard es una vista del servidor actual. Los conteos del archivo incluyen duplicados, mientras que las gráficas de actividad del dashboard cuentan solo eventos aceptados. La prueba de idempotencia del informe reenvía una compra al final y añade un duplicado únicamente a las estadísticas finales de `evidencia.json`.

El informe ya generado en `results/flujo_10K/informe/` usa `data/prepared/perfil_10K`, mientras que los comandos de esta guía usan 1K. Para comparar con ese informe existente, cambia `perfil_1K` por `perfil_10K` tanto al iniciar la API como al enviar eventos.

La preparación trabaja por bloques; la API y el análisis mantienen estado en memoria. Usa 1K para esta demostración: generar 1M o 10M no garantiza que todas las etapas puedan procesarlos con la misma memoria.

## Pruebas y referencias

Para ejecutar las pruebas:

```sh
python -m unittest discover -s tests -v
```

- [Dashboard](dashboard/README.md): opciones de la interfaz y actualización.
- [Plan del proyecto](docs/plan_proyecto.md): arquitectura, estructuras y alcance.
- [Plan de experimentación](docs/plan_experimentacion.md): métricas y evaluación por escala.
- [Configuración de preparación](configs/prepare.json) y [reproducción](configs/replay.json).
