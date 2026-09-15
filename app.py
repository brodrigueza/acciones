import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# (Opcional) Configura la página para usar todo el ancho de la pantalla
st.set_page_config(page_title="Dashboard Portafolio", layout="wide")

# ==========================================
# 1. FUNCIONES PARA OBTENER DATOS DE YAHOO
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
# 2. CARGA DE DATOS
# ==========================================
# (Aquí asumo que ya tienes tu código que lee tu Excel, CSV o base de datos)
# df_portafolio = pd.read_excel("mis_inversiones.xlsx") 

# ==========================================
# 3. PROCESAMIENTO DE YFINANCE
# ==========================================
# Creamos las nuevas columnas consultando la caché
df_portafolio["Sector"] = df_portafolio["Ticker"].apply(obtener_sector)
df_portafolio["Nombre_Empresa"] = df_portafolio["Ticker"].apply(obtener_nombre)

# ==========================================
# 4. MÉTRICAS FINANCIERAS (CORREGIDAS)
# ==========================================
col1, col2, col3, col4 = st.columns(4)

costo_global = df_portafolio["Costo_Total_CLP"].sum()
valor_invertido_global = df_portafolio["Valor_Posicion_CLP"].sum()
caja_dividendos_nacionales = df_portafolio["Dividendos_Cash_CLP"].sum()

costo_global_div = costo_global - caja_dividendos_nacionales
patrimonio_total = valor_invertido_global
ganancia_neta_global = patrimonio_total - costo_global_div

# Evitamos error de división por cero si el portafolio está vacío
rentabilidad_porcentaje = 0
if costo_global_div > 0:
    rentabilidad_porcentaje = (ganancia_neta_global / costo_global_div) * 100

col1.metric("Capital Aportado", f"${costo_global:,.0f}")
col2.metric("Valor Mercado (Acciones)", f"${patrimonio_total:,.0f}")
col3.metric("Dividendos Generados", f"${caja_dividendos_nacionales:,.0f}")
col4.metric("Ganancia Neta Total", f"${ganancia_neta_global:,.0f}", f"{rentabilidad_porcentaje:.2f}%")

st.divider() # Línea separadora visual

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
        hole=0.4 # Estilo Dona
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
