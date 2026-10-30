"""Dashboard Streamlit para observar la API de comercio electrónico.

Ejecutar desde la raíz del proyecto, con FastAPI ya iniciada:

    streamlit run dashboard/app.py
"""
from datetime import datetime
import os

import httpx
import streamlit as st


API_PREDETERMINADA = os.environ.get("ECOMMERCE_API_URL", "http://127.0.0.1:8000")


st.set_page_config(
    page_title="Ecommerce · Monitor en vivo",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.4rem; padding-bottom: 2rem;}
      [data-testid="stMetric"] {
        background: color-mix(in srgb, var(--background-color) 92%, #2563eb 8%);
        border: 1px solid rgba(128, 128, 128, .22);
        border-radius: .7rem;
        padding: .75rem 1rem;
      }
      .estado-vivo {color: #16a34a; font-weight: 700;}
      .estado-pausa {color: #d97706; font-weight: 700;}
      .pie {color: #6b7280; font-size: .82rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def obtener_json(cliente, ruta, params=None):
    respuesta = cliente.get(ruta, params=params)
    respuesta.raise_for_status()
    return respuesta.json()


def obtener_snapshot(api_url, minutos, limite):
    """Consulta las vistas públicas; un fallo no deja datos parciales ambiguos."""
    with httpx.Client(base_url=api_url.rstrip("/"), timeout=3.0) as cliente:
        salud = obtener_json(cliente, "/salud")
        panel = obtener_json(cliente, "/panel", {"minutos": minutos, "k": limite})
        estadisticas = obtener_json(cliente, "/admin/estadisticas")
        fraude = obtener_json(cliente, "/fraude/estadisticas")
        pares = obtener_json(cliente, "/cocompra/pares", {"k": limite})
        comunidades = obtener_json(
            cliente, "/cocompra/comunidades", {"min_tamano": 2, "limite": limite}
        )
    return {
        "salud": salud,
        "panel": panel,
        "estadisticas": estadisticas,
        "fraude": fraude,
        "pares": pares,
        "comunidades": comunidades,
    }


def tabla_metricas_servicios(estadisticas):
    filas = []
    for servicio, valores in estadisticas.items():
        if servicio == "carga" or not isinstance(valores, dict):
            continue
        fila = {"servicio": servicio}
        for clave, valor in valores.items():
            if isinstance(valor, (str, int, float, bool)) or valor is None:
                fila[clave] = valor
        filas.append(fila)
    return filas


def renderizar(snapshot):
    panel = snapshot["panel"]
    ventas = panel["ventas"]
    ingesta = panel.get("ingesta") or {}
    alertas = panel["alertas"]
    cola = panel["cola_ordenes"]
    carga = snapshot["salud"].get("carga") or {}
    st.caption(
        f"Datos: {carga.get('directorio', 'sin carpeta configurada')} · "
        f"Eventos precargados: {carga.get('eventos_precargados', 0):,} · "
        "Estado acumulado de esta API en memoria"
    )

    kpis = st.columns(6)
    kpis[0].metric("Aceptados", f"{ingesta.get('aceptados', 0):,}")
    kpis[1].metric("Duplicados", f"{ingesta.get('duplicados', 0):,}")
    kpis[2].metric("Rechazados", f"{ingesta.get('rechazados', 0):,}")
    kpis[3].metric("Ventas netas", f"{ventas.get('monto_neto', '0.00')}")
    kpis[4].metric("Alertas de pago", f"{alertas.get('total', 0):,}")
    kpis[5].metric("En cola", f"{cola.get('en_cola', 0):,}")

    tab_resumen, tab_eventos, tab_fraude, tab_cocompra, tab_sistema = st.tabs(
        ["Resumen", "Actividad y cola", "Fraude", "Co-compra", "Sistema"]
    )

    with tab_resumen:
        izquierda, derecha = st.columns((3, 2))
        with izquierda:
            st.subheader("Actividad por minuto")
            actividad = panel["actividad"].get("por_minuto", [])
            if actividad:
                st.line_chart(actividad, x="minuto", y="eventos", height=300)
            else:
                st.info("Envía tráfico para construir la serie de actividad.")
        with derecha:
            st.subheader("Eventos por tipo")
            por_tipo = panel["actividad"].get("por_tipo", {})
            if por_tipo:
                st.bar_chart(
                    [{"tipo": tipo, "eventos": cantidad} for tipo, cantidad in por_tipo.items()],
                    x="tipo",
                    y="eventos",
                    height=300,
                )
            else:
                st.info("Todavía no hay eventos aceptados.")

        izquierda, derecha = st.columns(2)
        with izquierda:
            st.subheader("Productos por ventas")
            productos = panel.get("top_productos_por_ventas", [])
            st.dataframe(productos, use_container_width=True, hide_index=True)
        with derecha:
            st.subheader("Productos por popularidad")
            populares = panel.get("top_productos_por_popularidad", [])
            st.dataframe(populares, use_container_width=True, hide_index=True)

    with tab_eventos:
        izquierda, derecha = st.columns(2)
        with izquierda:
            st.subheader("Próximos elementos de la cola")
            siguientes = cola.get("siguientes", [])
            if siguientes:
                st.dataframe(siguientes, use_container_width=True, hide_index=True)
            else:
                st.info("La cola de prioridad está vacía.")
        with derecha:
            st.subheader("Calidad de la ingesta")
            st.json(ingesta, expanded=True)
        st.subheader("Motivos de rechazo")
        motivos = ingesta.get("motivos_rechazo", {})
        if motivos:
            st.bar_chart(
                [{"motivo": motivo, "eventos": cantidad} for motivo, cantidad in motivos.items()],
                x="motivo",
                y="eventos",
            )
        else:
            st.caption("No se han registrado rechazos.")

    with tab_fraude:
        st.caption("Alertas por orden señalada; no equivalen a fraudes confirmados ni a intentos de pago.")
        col_total, col_bloqueos, col_revision = st.columns(3)
        col_total.metric("Alertas", f"{alertas.get('total', 0):,}")
        col_bloqueos.metric("Bloqueadas", f"{alertas.get('bloqueos', 0):,}")
        col_revision.metric("En revisión", f"{alertas.get('total', 0) - alertas.get('bloqueos', 0):,}")
        izquierda, derecha = st.columns((3, 2))
        with izquierda:
            st.subheader("Alertas recientes")
            recientes = alertas.get("recientes", [])
            if recientes:
                st.dataframe(recientes, use_container_width=True, hide_index=True)
            else:
                st.info("No hay alertas de fraude.")
        with derecha:
            st.subheader("Estado del detector")
            st.json(snapshot["fraude"], expanded=True)

    with tab_cocompra:
        izquierda, derecha = st.columns(2)
        with izquierda:
            st.subheader("Pares más comprados juntos")
            if snapshot["pares"]:
                st.dataframe(snapshot["pares"], use_container_width=True, hide_index=True)
            else:
                st.info("Aún no hay relaciones de co-compra.")
        with derecha:
            st.subheader("Comunidades de productos")
            comunidades = snapshot["comunidades"]
            st.metric("Modularidad", comunidades.get("modularidad", 0))
            st.metric("Comunidades", comunidades.get("comunidades_totales", 0))
            st.dataframe(
                comunidades.get("comunidades", []), use_container_width=True, hide_index=True
            )

    with tab_sistema:
        st.subheader("Servicios y estructuras")
        filas = tabla_metricas_servicios(snapshot["estadisticas"])
        st.dataframe(filas, use_container_width=True, hide_index=True)
        with st.expander("Carga inicial"):
            st.json(snapshot["salud"].get("carga", {}), expanded=True)


if "monitor_activo" not in st.session_state:
    st.session_state.monitor_activo = True

st.sidebar.header("Monitor")
api_url = st.sidebar.text_input("URL de FastAPI", API_PREDETERMINADA)
intervalo = st.sidebar.slider("Actualizar cada (segundos)", 1, 10, 2)
minutos = st.sidebar.slider("Últimos minutos con actividad", 5, 180, 30)
limite = st.sidebar.slider("Elementos por lista", 5, 50, 10)

col_iniciar, col_pausar = st.sidebar.columns(2)
if col_iniciar.button("Iniciar", use_container_width=True, disabled=st.session_state.monitor_activo):
    st.session_state.monitor_activo = True
    st.rerun()
if col_pausar.button("Pausar", use_container_width=True, disabled=not st.session_state.monitor_activo):
    st.session_state.monitor_activo = False
    st.rerun()

st.title("Monitor de eventos de ecommerce")
st.caption("FastAPI → Ingesta → Catálogo → Fraude → Priorización → Co-compra → Recomendación → Panel")

cada = intervalo if st.session_state.monitor_activo else None


@st.fragment(run_every=cada)
def monitor():
    estado = "<span class='estado-vivo'>● EN VIVO</span>" if st.session_state.monitor_activo else "<span class='estado-pausa'>● EN PAUSA</span>"
    st.markdown(estado, unsafe_allow_html=True)
    try:
        snapshot = obtener_snapshot(api_url, minutos, limite)
    except (httpx.HTTPError, ValueError) as error:
        st.error(
            f"No se pudo consultar {api_url}. Inicia FastAPI con "
            "`uvicorn API_SERVICIOS.main:app --reload`."
        )
        st.caption(f"Detalle: {error}")
        return
    renderizar(snapshot)
    st.markdown(
        f"<p class='pie'>Última consulta: {datetime.now().astimezone().strftime('%H:%M:%S %Z')}</p>",
        unsafe_allow_html=True,
    )


monitor()

