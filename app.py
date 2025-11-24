import streamlit as st
import pandas as pd
import altair as alt
from statsmodels.tsa.arima.model import ARIMA
from streamlit_autorefresh import st_autorefresh

# --- Auto refresh ---
st_autorefresh(interval=60 * 1000, key="data_refresh")

# --- Page setup ---
st.set_page_config(page_title="Buff163 Price Tracker", layout="wide")
st.title("💰 Buff163 Price Tracker Dashboard")

# --- Load data with cache ---
@st.cache_data(ttl=60)
def load_data():
    url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTr7Aw-OEINPz2QrxhhHlJjv7TQufk0DPg1LnlPP_MyCzzRsdZCCd1UI4JAySPRrsIwRSVyltFd6bLM/pub?gid=1708877950&single=true&output=csv"
    df = pd.read_csv(url)
    return df

# --- Load dataset ---
try:
    df = load_data()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

# --- Cleaning ---
if "Date" not in df.columns or "Skin Name" not in df.columns:
    st.error("Missing required columns in the Google Sheet.")
    st.stop()

df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
df = df.dropna(subset=["Date"])
df = df.sort_values("Date")

# --- Sidebar ---
st.sidebar.header("Filters")
skin_list = df["Skin Name"].dropna().unique()

if len(skin_list) == 0:
    st.error("No skins found in the dataset.")
    st.stop()

skin_selected = st.sidebar.selectbox("Select a skin", skin_list)

# --- Filter data ---
filtered = df[df["Skin Name"] == skin_selected]

if filtered.empty:
    st.warning("No data available for this skin.")
    st.stop()

# --- Trend Chart ---
st.subheader(f"📈 Price trend: {skin_selected}")

try:
    chart = (
        alt.Chart(filtered)
        .mark_line(point=True)
        .encode(
            x="Date:T",
            y="Price:Q",
            tooltip=["Date", "Price", "Listings"]
        )
        .properties(height=400)
        .interactive()
    )
    st.altair_chart(chart, use_container_width=True)
except Exception as e:
    st.error(f"Failed to render chart: {e}")

# --- Latest stats ---
try:
    latest = filtered.iloc[-1]
    st.metric("Current Price", f"{latest['Price']:.2f}")
    st.metric("Listings", int(latest["Listings"]))
except Exception:
    st.warning("Cannot display metrics for this skin.")

# --- Forecast ---
if st.sidebar.checkbox("Show Forecast (ARIMA)"):

    series = filtered["Price"].dropna()

    # Must have enough data
    if len(series) < 10:
        st.warning("Not enough data to generate ARIMA forecast (need ≥10 points).")
        st.stop()

    try:
        model = ARIMA(series, order=(1, 1, 1))
        fit = model.fit()

        forecast = fit.forecast(steps=7)

        forecast_df = pd.DataFrame({
            "Date": pd.date_range(
                start=filtered["Date"].iloc[-1] + pd.Timedelta(days=1),
                periods=7,
                freq="D"
            ),
            "Forecast": forecast
        })

        st.subheader("🔮 7-Day Price Forecast")

        forecast_chart = (
            alt.Chart(forecast_df)
            .mark_line(color="orange")
            .encode(x="Date:T", y="Forecast:Q")
        )

        st.altair_chart(forecast_chart, use_container_width=True)

    except Exception as e:
        st.error(f"Forecast failed: {e}")
