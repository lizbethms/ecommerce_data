# Dashboard Streamlit

Monitor de solo lectura para los servicios de `API_SERVICIOS`. Consulta FastAPI
periódicamente y muestra ingesta, ventas, actividad, cola, fraude, co-compra y
estadísticas de las estructuras.

## Ejecución

Sigue los tres comandos de [README.md](../README.md#5-iniciar-la-api-el-dashboard-y-el-tráfico).
Usa el mismo `events.parquet` para el informe y la API y espera a que termine el cliente antes de comparar los conteos.

Streamlit abre normalmente `http://localhost:8501`. La URL de la API y el
intervalo de actualización se pueden cambiar desde la barra lateral. También se
puede definir otra URL antes de iniciar la interfaz:

```sh
ECOMMERCE_API_URL=http://127.0.0.1:8000 streamlit run dashboard/app.py
```

El dashboard usa consultas HTTP periódicas. Su estado es acumulado y vive en la
API actual. Las alertas son órdenes señaladas para revisión o bloqueo, no casos
de fraude confirmados. La actividad por tipo incluye solo eventos aceptados;
el control «Últimos minutos con actividad» muestra los últimos minutos que
tuvieron eventos según `event_time`, no una ventana continua de reloj.

