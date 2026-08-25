import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

st.set_page_config(page_title="Dashboard de Inversiones - DRIP", layout="wide")

@st.cache_data(ttl=3600)
def obtener_tipo_cambio():
    """Obtiene el valor del dólar observado (USD a CLP)."""
    try:
        usd_clp = yf.Ticker("CLP=X").history(period="1d")['Close'].iloc[-1]
        return float(usd_clp)
    except:
        st.warning("No se pudo obtener tipo de cambio. Usando $900 por defecto.")
        return 900.0

@st.cache_data(ttl=3600)
def obtener_datos_mercado(tickers):
    """Descarga el historial completo de precios y dividendos."""
    precios_actuales = {}
    historial_dividendos = {}
    historial_precios = {}
    
    for t in tickers:
        try:
            stock = yf.Ticker(t)
            hist = stock.history(period="max") 
            
            if not hist.empty:
                precios_actuales[t] = float(hist['Close'].iloc[-1])
                hist.index = pd.to_datetime(hist.index, utc=True)
                historial_precios[t] = hist['Close']
            else:
                precios_actuales[t] = None
                historial_precios[t] = pd.Series(dtype=float)
                
            divs = stock.dividends
            if not divs.empty:
                divs.index = pd.to_datetime(divs.index, utc=True)
                historial_dividendos[t] = divs
            else:
                historial_dividendos[t] = pd.Series(dtype=float)
                
        except Exception as e:
            precios_actuales[t] = None
            historial_dividendos[t] = pd.Series(dtype=float)
            historial_precios[t] = pd.Series(dtype=float)
            
    return precios_actuales, historial_dividendos, historial_precios

def simular_posicion_drip(row, dividendos_dict, precios_hist_dict):
    """
    Calcula reinversión (DRIP) para acciones extranjeras 
    y flujo de caja para acciones nacionales.
    """
    ticker = row["Ticker"]
    fecha_compra = row["Fecha_Compra"]
    cantidad_inicial = row["Cantidad"]
    es_nacional = str(ticker).endswith(".SN")
    
    serie_div = dividendos_dict.get(ticker, pd.Series(dtype=float))
    serie_precios = precios_hist_dict.get(ticker, pd.Series(dtype=float))
    
    divs_validos = serie_div[serie_div.index >= fecha_compra] if not serie_div.empty else pd.Series(dtype=float)
        
    if es_nacional or divs_validos.empty or serie_precios.empty:
        # Cobrar en efectivo (Caja)
        cash_generado = divs_validos.sum() * cantidad_inicial
        return pd.Series({"Cantidad_Final": cantidad_inicial, "Dividendos_Cash": cash_generado})
    else:
        # Lógica DRIP (Interés compuesto)
        acciones_actuales = float(cantidad_inicial)
        for fecha_div, monto_div in divs_validos.items():
            precio_fecha = serie_precios.asof(fecha_div) 
            if pd.notna(precio_fecha) and precio_fecha > 0:
                cash_recibido = acciones_actuales * monto_div
                nuevas_acciones = cash_recibido / precio_fecha
                acciones_actuales += nuevas_acciones
                
        return pd.Series({"Cantidad_Final": acciones_actuales, "Dividendos_Cash": 0.0})

# --- INTERFAZ DEL DASHBOARD ---

st.title("📊 Portafolio Consolidado (DRIP & Multimoneda)")
st.markdown("Las acciones internacionales reinvierten dividendos automáticamente. Las nacionales generan liquidez (Caja).")

archivo_excel = st.file_uploader("Cargar transacciones (Excel)", type=["xlsx", "xls"], accept_multiple_files=True)

if archivo_excel:
    try:
        df_list = [pd.read_excel(file) for file in archivo_excel]
        df_transacciones = pd.concat(df_list, ignore_index=True)
        
        # 1. Corrección de columnas invertidas
        if pd.api.types.is_datetime64_any_dtype(df_transacciones.get("Precio_Compra")) or \
           pd.api.types.is_numeric_dtype(df_transacciones.get("Fecha_Compra")):
            df_transacciones = df_transacciones.rename(columns={
                "Precio_Compra": "Fecha_Compra_Temp",
                "Fecha_Compra": "Precio_Compra"
            }).rename(columns={"Fecha_Compra_Temp": "Fecha_Compra"})
            
        df_transacciones["Fecha_Compra"] = pd.to_datetime(df_transacciones["Fecha_Compra"], utc=True)
        
        # 2. SOLUCIÓN STREAMLIT CLOUD (Convertir a tuple para evitar error de Hash)
        tickers_unicos = tuple(df_transacciones["Ticker"].unique())
        
        tipo_cambio_actual = obtener_tipo_cambio()
        st.info(f"Dólar actual: ${tipo_cambio_actual:,.2f} CLP | Calculando histórico de dividendos y reinversiones...")
        
        precios_dict, dividendos_dict, precios_hist_dict = obtener_datos_mercado(tickers_unicos)

        df_transacciones["Precio_Actual"] = df_transacciones["Ticker"].map(precios_dict)
        df_transacciones = df_transacciones.dropna(subset=["Precio_Actual"]).copy()
        
        # 3. Factor de conversión de moneda
        df_transacciones["Factor_CLP"] = df_transacciones["Ticker"].apply(lambda x: 1 if str(x).endswith(".SN") else tipo_cambio_actual)

        # 4. Simulación DRIP
        res_drip = df_transacciones.apply(lambda row: simular_posicion_drip(row, dividendos_dict, precios_hist_dict), axis=1)
        df_transacciones["Cantidad_Final"] = res_drip["Cantidad_Final"]
        df_transacciones["Dividendos_Lote_Original"] = res_drip["Dividendos_Cash"]

        # 5. Cálculos Finales en CLP
        df_transacciones["Costo_Lote_CLP"] = (df_transacciones["Cantidad"] * df_transacciones["Precio_Compra"]) * df_transacciones["Factor_CLP"]
        df_transacciones["Valor_Actual_Lote_CLP"] = (df_transacciones["Cantidad_Final"] * df_transacciones["Precio_Actual"]) * df_transacciones["Factor_CLP"]
        df_transacciones["Dividendos_Lote_CLP"] = df_transacciones["Dividendos_Lote_Original"] * df_transacciones["Factor_CLP"]

        # 6. Agrupación por Ticker
        df_portafolio = df_transacciones.groupby("Ticker").agg(
            Acciones_Iniciales=("Cantidad", "sum"),
            Acciones_Actuales=("Cantidad_Final", "sum"),
            Costo_Total_CLP=("Costo_Lote_CLP", "sum"),
            Valor_Posicion_CLP=("Valor_Actual_Lote_CLP", "sum"),
            Dividendos_Cash_CLP=("Dividendos_Lote_CLP", "sum")
        ).reset_index()

        df_portafolio["Ganancia_Capital_CLP"] = df_portafolio["Valor_Posicion_CLP"] - df_portafolio["Costo_Total_CLP"]
        df_portafolio["Ganancia_Total_CLP"] = df_portafolio["Ganancia_Capital_CLP"] + df_portafolio["Dividendos_Cash_CLP"]
        df_portafolio["Rentabilidad_Total_%"] = (df_portafolio["Ganancia_Total_CLP"] / df_portafolio["Costo_Total_CLP"]) * 100

        # --- MÉTRICAS ---
        col1, col2, col3, col4 = st.columns(4)
        costo_global = df_portafolio["Costo_Total_CLP"].sum()
        valor_invertido_global = df_portafolio["Valor_Posicion_CLP"].sum()
        caja_dividendos_nacionales = df_portafolio["Dividendos_Cash_CLP"].sum()
        
        patrimonio_total = valor_invertido_global + caja_dividendos_nacionales
        ganancia_neta_global = patrimonio_total - costo_global

        col1.metric("Capital Aportado", f"${costo_global:,.0f}")
        col2.metric("Valor Mercado (Acciones)", f"${valor_invertido_global:,.0f}")
        col3.metric("Caja Liquida (Div. Nac.)", f"${caja_dividendos_nacionales:,.0f}")
        col4.metric("Patrimonio Total", f"${patrimonio_total:,.0f}", f"{(ganancia_neta_global/costo_global)*100:.2f}%")

        st.divider()

        # --- VISUALIZACIÓN ---
        col_graf, col_tabla = st.columns([1, 2])

        with col_graf:
            st.subheader("Distribución Patrimonial Real")
            
            df_grafico = df_portafolio[['Ticker', 'Valor_Posicion_CLP']].copy()
            df_grafico = df_grafico.rename(columns={'Valor_Posicion_CLP': 'Valor'})
            
            if caja_dividendos_nacionales > 0:
                fila_caja = pd.DataFrame({'Ticker': ['CAJA (Efectivo)'], 'Valor': [caja_dividendos_nacionales]})
                df_grafico = pd.concat([df_grafico, fila_caja], ignore_index=True)
            
            # Clasificación para el gráfico macro
            df_grafico['Mercado'] = df_grafico['Ticker'].apply(
                lambda x: 'Efectivo Disponible' if x == 'CAJA (Efectivo)' else ('Mercado Chileno' if str(x).endswith('.SN') else 'Mercado Internacional')
            )
            
            # Torta 1: Por Mercado
            fig_mercado = px.pie(df_grafico, values='Valor', names='Mercado', title="Exposición por Mercado", 
                                 color_discrete_sequence=px.colors.qualitative.Set2)
            st.plotly_chart(fig_mercado, use_container_width=True)
            
            # Torta 2: Por Acción
            fig_accion = px.pie(df_grafico, values='Valor', names='Ticker', hole=0.4, title="Exposición por Activo",
                                color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_accion.update_traces(textposition='inside', textinfo='percent+label', showlegend=False)
            st.plotly_chart(fig_accion, use_container_width=True)

        with col_tabla:
            st.subheader("Desglose Consolidado")
            st.dataframe(df_portafolio.style.format({
                "Acciones_Iniciales": "{:,.2f}",
                "Acciones_Actuales": "{:,.4f}",
                "Costo_Total_CLP": "${:,.0f}",
                "Valor_Posicion_CLP": "${:,.0f}",
                "Dividendos_Cash_CLP": "${:,.0f}",
                "Ganancia_Total_CLP": "${:,.0f}",
                "Rentabilidad_Total_%": "{:.2f}%"
            }), use_container_width=True)

    except Exception as e:
        st.error(f"Error procesando los datos: {e}")
else:
    st.info("👆 Sube tus archivos Excel para procesar tu portafolio.")
