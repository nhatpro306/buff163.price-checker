import streamlit as st
import pandas as pd
import altair as alt
from statsmodels.tsa.arima.model import ARIMA
import requests

# -------------------------------
# PAGE CONFIG
# -------------------------------
st.set_page_config(page_title="Buff163 Price Tracker", layout="wide")
st.title("💰 Buff163 Price Tracker Dashboard")

# -------------------------------
# SAFE DATA LOADER (Sheet.best JSON API)
# -------------------------------
@st.cache_data(ttl=300)  # cache 5 minutes
def load_data():
    url = "https://sheet.best/api/sheets/YOUR_SHEET_ID"  # Replace with your Sheet.best URL
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data)

        # Clean & validate
        if "Date" not in df.columns or "Skin Name" not in df.columns:
            st.error("❌ Missing required columns in sheet data")
            return pd.DataFrame()

        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
        df = df.sort_values("Date")
        return df
    except Exception as e:
        st.error(f"❌ Failed to load data: {e}")
        return pd.DataFrame()

# Load data
df = load_data()
if df.empty:
    st.warning("⚠ No data available")
    st.stop()

# -------------------------------
# SIDEBAR FILTER
# -------------------------------
st.sidebar.header("Filters")
skin_list = df["Skin Name"].dropna().unique()
skin_selected = st.sidebar.selectbox("Select a skin", skin_list)

filtered = df[df["Skin Name"] == skin_selected]
if filtered.empty:
    st.warning("⚠ No data for this skin")
    st.stop()

# -------------------------------
# PRICE TREND CHART
# -------------------------------
st.subheader(f"📈 Price Trend: {skin_selected}")
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

# -------------------------------
# STATS METRICS
# -------------------------------
latest = filtered.iloc[-1]
col1, col2 = st.columns(2)
col1.metric("Current Price", f"{latest['Price']:.2f}")
col2.metric("Listings", int(latest["Listings"]))

# -------------------------------
# FORECAST (ARIMA)
# -------------------------------
st.sidebar.subheader("Forecast Options")
do_forecast = st.sidebar.checkbox("Enable Forecast (ARIMA)")

if do_forecast:
    series = filtered["Price"].dropna()
    if len(series) < 10:
        st.warning("⚠ Not enough data for ARIMA forecast")
    else:
        try:
            if st.button("Run 7-Day Forecast"):
                with st.spinner("Generating ARIMA forecast..."):
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
                        .encode(
                            x="Date:T",
                            y="Forecast:Q"
                        )
                        .properties(height=300)
                    )
                    st.altair_chart(forecast_chart, use_container_width=True)
        except Exception as e:
            st.error(f"❌ ARIMA Forecast failed: {e}")
