import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# Configuración básica de la página para aprovechar la pantalla completa
st.set_page_config(page_title="Mi Portafolio", layout="wide")

# ==========================================
# 1. FUNCIONES PARA OBTENER DATOS (EN CACHÉ)
# ==========================================
@st.cache_data
def obtener_sector(ticker):
    try:
        info = yf.Ticker(ticker).info
        if info.get('quoteType') == 'ETF':
            return info.get('category', 'ETF')
        return info.get('sector', 'Desconocido')
    except Exception:
        return "Desconocido"

@st.cache_data
def obtener_nombre(ticker):
    try:
        return yf.Ticker(ticker).info.get('shortName', ticker)
    except:
        return ticker

# ==========================================
# 2. INTERFAZ DE CARGA DE DATOS
# ==========================================
st.title("📊 Dashboard de Inversiones")

# Ventana para buscar el archivo en el ordenador
archivo_subido = st.file_uploader(
    "Sube tu archivo de datos (Parquet o Excel)", 
    type=["parquet", "xlsx", "xls"]
)

# Todo el código principal se ejecuta SOLAMENTE si ya se subió un archivo
if archivo_subido is not None:
    
    # Leemos el archivo dependiendo de su formato
    if archivo_subido.name.endswith('.parquet'):
        df_portafolio = pd.read_parquet(archivo_subido)
    else:
        df_portafolio = pd.read_excel(archivo_subido)

    # ==========================================
    # 3. PROCESAMIENTO CON YFINANCE
    # ==========================================
    # st.spinner muestra un mensaje visual mientras se descargan los datos
    with st.spinner("Consultando datos de sectores en Yahoo Finance..."):
        df_portafolio["Sector"] = df_portafolio["Ticker"].apply(obtener_sector)
        df_portafolio["Nombre_Empresa"] = df_portafolio["Ticker"].apply(obtener_nombre)

    # ==========================================
    # 4. MÉTRICAS FINANCIERAS
    # ==========================================
    st.subheader("Resumen General")
    col1, col2, col3, col4 = st.columns(4)
    
    costo_global = df_portafolio["Costo_Total_CLP"].sum()
    valor_invertido_global = df_portafolio["Valor_Posicion_CLP"].sum()
    caja_dividendos_nacionales = df_portafolio["Dividendos_Cash_CLP"].sum()

    costo_global_div = costo_global - caja_dividendos_nacionales
    patrimonio_total = valor_invertido_global
    ganancia_neta_global = patrimonio_total - costo_global_div

    # Evitar división por cero
    rentabilidad_porcentaje = 0
    if costo_global_div > 0:
        rentabilidad_porcentaje = (ganancia_neta_global / costo_global_div) * 100

    col1.metric("Capital Aportado", f"${costo_global:,.0f}")
    col2.metric("Valor Mercado (Acciones)", f"${patrimonio_total:,.0f}")
    col3.metric("Dividendos Generados", f"${caja_dividendos_nacionales:,.0f}")
    col4.metric("Ganancia Neta Total", f"${ganancia_neta_global:,.0f}", f"{rentabilidad_porcentaje:.2f}%")

    st.divider()

    # ==========================================
    # 5. DASHBOARD DE GRÁFICOS (Lado a Lado)
    # ==========================================
    graf_col1, graf_col2 = st.columns(2)

    with graf_col1:
        st.subheader("Composición por Activo")
        fig_activos = px.pie(
            df_portafolio,
            values="Valor_Posicion_CLP",
            names="Ticker",
            custom_data=["Nombre_Empresa", "Sector"]
        )
        fig_activos.update_traces(
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>" +
                "Valor actual: $%{value:,.0f}<br>" +
                "Sector: %{customdata[1]}<br>" +
                "Peso en portafolio: %{percent}<br>" +
                "<extra></extra>"
            )
        )
        st.plotly_chart(fig_activos, use_container_width=True)

    with graf_col2:
        st.subheader("Diversificación por Sector")
        fig_sectores = px.pie(
            df_portafolio,
            values="Valor_Posicion_CLP",
            names="Sector",
            hole=0.4 # Gráfico estilo dona
        )
        fig_sectores.update_traces(
            hovertemplate=(
                "<b>Sector: %{label}</b><br>" +
                "Valor invertido: $%{value:,.0f}<br>" +
                "Porcentaje: %{percent}<br>" +
                "<extra></extra>"
            )
        )
        st.plotly_chart(fig_sectores, use_container_width=True)

else:
    # Mensaje inicial cuando entras a la app y aún no subes nada
    st.info("👆 Por favor, selecciona y carga tu archivo (Excel o Parquet) usando el botón de arriba.")
