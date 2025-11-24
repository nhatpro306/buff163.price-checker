import streamlit as st
import requests
import pandas as pd
import altair as alt
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# -------------------------------
# PAGE CONFIG
# -------------------------------
st.set_page_config(page_title="Buff.163 Live Tracker", layout="wide")
st.title("💰 Buff.163 Live CS:GO Skin Price Tracker")

# -------------------------------
# AUTO REFRESH EVERY 12 HOURS
# -------------------------------
# 12 hours = 12*60*60*1000 milliseconds = 43,200,000 ms
st_autorefresh(interval=43_200_000, key="auto_refresh_12h")

# -------------------------------
# SKINS CONFIG (replace with real Buff IDs)
# -------------------------------
SKINS = {
    "Butterfly Knife | Fade": 123456,
    "Karambit | Doppler": 234567,
}

skin_selected = st.sidebar.selectbox("Select a skin", list(SKINS.keys()))
skin_id = SKINS[skin_selected]

# Price alert threshold
threshold = st.sidebar.number_input(
    "Alert if price drops below:", value=150.0, step=1.0
)

# -------------------------------
# FETCH LIVE PRICES FUNCTION
# -------------------------------
def fetch_live_prices(skin_id):
    url = f"https://buff.163.com/api/market/goods/sell_order?game=csgo&goods_id={skin_id}&sort_by=default"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        prices = [float(item["price"]) for item in data["data"]["items"]]
        return prices
    except Exception as e:
        st.error(f"Failed to fetch prices: {e}")
        return []

# -------------------------------
# FETCH AND DISPLAY PRICES
# -------------------------------
prices = fetch_live_prices(skin_id)

if prices:
    df = pd.DataFrame({
        "Date": [datetime.now()]*len(prices),
        "Price": prices
    })

    # Show price table
    st.subheader(f"📋 Latest Listings for {skin_selected}")
    st.dataframe(df)

    # Show price distribution chart
    st.subheader("📊 Price Distribution")
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X("Price:Q", bin=alt.Bin(maxbins=30), title="Price"),
        y=alt.Y("count()", title="Number of Listings")
    )
    st.altair_chart(chart, use_container_width=True)

    # Show metrics
    st.subheader("💵 Key Metrics")
    st.metric("Lowest Price", f"{df['Price'].min():.2f}")
    st.metric("Highest Price", f"{df['Price'].max():.2f}")
    st.metric("Average Price", f"{df['Price'].mean():.2f}")

    # Price alert
    if df['Price'].min() < threshold:
        st.warning(f"⚠ Price dropped below {threshold}! Current lowest: {df['Price'].min():.2f}")
else:
    st.warning("No data fetched yet.")
