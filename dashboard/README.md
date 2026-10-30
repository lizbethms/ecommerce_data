# Dashboard Streamlit

Monitor de solo lectura para los servicios de `API_SERVICIOS`. Consulta FastAPI
periódicamente y muestra ingesta, ventas, actividad, cola, fraude, co-compra y
estadísticas de las estructuras.

## Ejecución

Desde la raíz del proyecto, en tres terminales:

```sh
# Terminal 1: API
uvicorn API_SERVICIOS.main:app --reload

# Terminal 2: interfaz
streamlit run dashboard/app.py

# Terminal 3: tráfico de demostración
python -m API_SERVICIOS.cliente_trafico --tasa 100 --lote 20 --reenvios 0.02 --invalidos 0.01
```

Streamlit abre normalmente `http://localhost:8501`. La URL de la API y el
intervalo de actualización se pueden cambiar desde la barra lateral. También se
puede definir otra URL antes de iniciar la interfaz:

```sh
ECOMMERCE_API_URL=http://127.0.0.1:8000 streamlit run dashboard/app.py
```

El dashboard usa polling HTTP. No modifica el estado de la API ni inicia el
generador de tráfico. Para visualizar cada evento individual atravesando los
servicios haría falta añadir un canal WebSocket de telemetría.

