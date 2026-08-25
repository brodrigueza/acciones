import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

st.set_page_config(page_title="Dashboard de Inversiones - DRIP", layout="wide")

@st.cache_data(ttl=3600)
def obtener_tipo_cambio():
    try:
        usd_clp = yf.Ticker("CLP=X").history(period="1d")['Close'].iloc[-1]
        return float(usd_clp)
    except:
        st.warning("No se pudo obtener tipo de cambio. Usando $900 por defecto.")
        return 900.0

@st.cache_data(ttl=3600)
def obtener_datos_mercado(tickers):
    """
    Ahora también extrae el historial de precios completo para poder
    simular las compras de reinversión en la fecha exacta del dividendo.
    """
    precios_actuales = {}
    historial_dividendos = {}
    historial_precios = {}
    
    for t in tickers:
        try:
            stock = yf.Ticker(t)
            hist = stock.history(period="max") 
            
            if not hist.empty:
                precios_actuales[t] = float(hist['Close'].iloc[-1])
                # Estandarizar zonas horarias a UTC
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
    Función matemática robusta para calcular la posición final.
    Acciones Nacionales -> Cobran cash.
    Acciones Internacionales -> Reinvierten a precio de mercado.
    """
    ticker = row["Ticker"]
    fecha_compra = row["Fecha_Compra"]
    cantidad_inicial = row["Cantidad"]
    es_nacional = str(ticker).endswith(".SN")
    
    serie_div = dividendos_dict.get(ticker, pd.Series(dtype=float))
    serie_precios = precios_hist_dict.get(ticker, pd.Series(dtype=float))
    
    divs_validos = serie_div[serie_div.index >= fecha_compra] if not serie_div.empty else pd.Series(dtype=float)
        
    if es_nacional or divs_validos.empty or serie_precios.empty:
        # Comportamiento tradicional: cobrar en efectivo
        cash_generado = divs_validos.sum() * cantidad_inicial
        return pd.Series({
            "Cantidad_Final": cantidad_inicial, 
            "Dividendos_Cash": cash_generado
        })
    else:
        # Lógica DRIP (Efecto Compuesto)
        acciones_actuales = float(cantidad_inicial)
        
        # Iteramos cronológicamente por cada dividendo pagado
        for fecha_div, monto_div in divs_validos.items():
            # .asof() busca el último precio de cierre válido hasta esa fecha
            precio_fecha = serie_precios.asof(fecha_div) 
            
            if pd.notna(precio_fecha) and precio_fecha > 0:
                # 1. ¿Cuánto dinero nos pagaron por las acciones que teníamos en ese momento?
                cash_recibido = acciones_actuales * monto_div
                # 2. ¿Cuántas acciones (o fracciones) compramos con ese dinero?
                nuevas_acciones = cash_recibido / precio_fecha
                # 3. Sumamos al patrimonio
                acciones_actuales += nuevas_acciones
                
        return pd.Series({
            "Cantidad_Final": acciones_actuales, 
            "Dividendos_Cash": 0.0 # Todo fue reinvertido
        })

# --- INTERFAZ DEL DASHBOARD ---

st.title("📊 Portafolio Consolidado (DRIP & Multimoneda)")
st.markdown("Las acciones internacionales reinvierten dividendos automáticamente. Las nacionales generan flujo de caja.")

archivo_excel = st.file_uploader("Cargar transacciones", type=["xlsx", "xls"], accept_multiple_files=True)

if archivo_excel:
    try:
        df_list = [pd.read_excel(file) for file in archivo_excel]
        df_transacciones = pd.concat(df_list, ignore_index=True)
        
        # Corrección de columnas invertidas
        if pd.api.types.is_datetime64_any_dtype(df_transacciones.get("Precio_Compra")) or \
           pd.api.types.is_numeric_dtype(df_transacciones.get("Fecha_Compra")):
            df_transacciones = df_transacciones.rename(columns={
                "Precio_Compra": "Fecha_Compra_Temp",
                "Fecha_Compra": "Precio_Compra"
            }).rename(columns={"Fecha_Compra_Temp": "Fecha_Compra"})
            
        df_transacciones["Fecha_Compra"] = pd.to_datetime(df_transacciones["Fecha_Compra"], utc=True)
        tickers_unicos = df_transacciones["Ticker"].unique()
        
        tipo_cambio_actual = obtener_tipo_cambio()
        st.info(f"Dólar actual: ${tipo_cambio_actual:,.2f} CLP | Calculando reinversiones históricas...")
        
        # Extraemos precios, dividendos y el historial completo de precios
        precios_dict, dividendos_dict, precios_hist_dict = obtener_datos_mercado(tickers_unicos)

        df_transacciones["Precio_Actual"] = df_transacciones["Ticker"].map(precios_dict)
        df_transacciones = df_transacciones.dropna(subset=["Precio_Actual"]).copy()
        df_transacciones["Factor_CLP"] = df_transacciones["Ticker"].apply(lambda x: 1 if str(x).endswith(".SN") else tipo_cambio_actual)

        # APLICAMOS LA SIMULACIÓN DRIP FILA POR FILA
        res_drip = df_transacciones.apply(lambda row: simular_posicion_drip(row, dividendos_dict, precios_hist_dict), axis=1)
        df_transacciones["Cantidad_Final"] = res_drip["Cantidad_Final"]
        df_transacciones["Dividendos_Lote_Original"] = res_drip["Dividendos_Cash"]

        # Cálculos de valorización con la NUEVA cantidad de acciones
        df_transacciones["Costo_Lote_CLP"] = (df_transacciones["Cantidad"] * df_transacciones["Precio_Compra"]) * df_transacciones["Factor_CLP"]
        df_transacciones["Valor_Actual_Lote_CLP"] = (df_transacciones["Cantidad_Final"] * df_transacciones["Precio_Actual"]) * df_transacciones["Factor_CLP"]
        df_transacciones["Dividendos_Lote_CLP"] = df_transacciones["Dividendos_Lote_Original"] * df_transacciones["Factor_CLP"]

        # Agrupación
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
        valor_global = df_portafolio["Valor_Posicion_CLP"].sum()
        dividendos_globales = df_portafolio["Dividendos_Cash_CLP"].sum()
        rentabilidad_global = (valor_global + dividendos_globales) - costo_global

        col1.metric("Capital Invertido", f"${costo_global:,.0f}")
        col2.metric("Valor Portafolio", f"${valor_global:,.0f}")
        col3.metric("Flujo Caja (Solo Nac.)", f"${dividendos_globales:,.0f}")
        col4.metric("Ganancia Total", f"${rentabilidad_global:,.0f}", f"{(rentabilidad_global/costo_global)*100:.2f}%")

        st.divider()

        st.subheader("Desglose Consolidado (Notarás que las acciones int. han crecido en cantidad)")
        st.dataframe(df_portafolio.style.format({
            "Acciones_Iniciales": "{:,.2f}",
            "Acciones_Actuales": "{:,.4f}",
            "Costo_Total_CLP": "{:,.0f}",
            "Valor_Posicion_CLP": "{:,.0f}",
            "Dividendos_Cash_CLP": "{:,.0f}",
            "Ganancia_Total_CLP": "{:,.0f}",
            "Rentabilidad_Total_%": "{:.2f}%"
        }), use_container_width=True)

    except Exception as e:
        st.error(f"Error procesando los datos: {e}")