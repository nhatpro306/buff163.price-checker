import streamlit as st
import pandas as pd
import altair as alt
from statsmodels.tsa.arima.model import ARIMA

from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=60 * 1000, key="data_refresh")


# --- Page setup ---
st.set_page_config(page_title="Buff163 Price Tracker", layout="wide")
st.title("💰 Buff163 Price Tracker Dashboard")

# --- Load data ---
sheet_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTr7Aw-OEINPz2QrxhhHlJjv7TQufk0DPg1LnlPP_MyCzzRsdZCCd1UI4JAySPRrsIwRSVyltFd6bLM/pub?gid=1708877950&single=true&output=csv"
df = pd.read_csv(sheet_url)

# --- Data cleaning ---
df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
df = df.sort_values('Date')

# --- Sidebar filters ---
st.sidebar.header("Filters")
skin_list = df['Skin Name'].dropna().unique()
skin_selected = st.sidebar.selectbox("Select a skin", skin_list)

# --- Filtered view ---
filtered = df[df['Skin Name'] == skin_selected]

st.subheader(f"📈 Price trend: {skin_selected}")
chart = (
    alt.Chart(filtered)
    .mark_line(point=True)
    .encode(
        x='Date:T',
        y='Price:Q',
        tooltip=['Date', 'Price', 'Listings']
    )
    .properties(height=400)
    .interactive()
)
st.altair_chart(chart, use_container_width=True)

# --- Stats summary ---
latest = filtered.iloc[-1]
st.metric(label="Current Price", value=f"{latest['Price']:.2f}")
st.metric(label="Listings", value=int(latest['Listings']))

# --- Forecast (optional) ---
if st.sidebar.checkbox("Show Forecast (ARIMA)"):
    try:
        series = filtered['Price'].dropna()
        model = ARIMA(series, order=(1, 1, 1))
        fit = model.fit()
        forecast = fit.forecast(steps=7)
        forecast_df = pd.DataFrame({
            'Date': pd.date_range(filtered['Date'].iloc[-1], periods=7, freq='D'),
            'Forecast': forecast
        })
        st.subheader("🔮 7-Day Price Forecast")
        forecast_chart = (
            alt.Chart(forecast_df)
            .mark_line(color='orange')
            .encode(x='Date:T', y='Forecast:Q')
        )
        st.altair_chart(forecast_chart, use_container_width=True)
    except Exception as e:
        st.error(f"Forecast failed: {e}")
