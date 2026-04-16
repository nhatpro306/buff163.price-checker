from __future__ import annotations

import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from gspread import WorksheetNotFound
from streamlit_autorefresh import st_autorefresh

from main import (
    CATALOG_HEADERS,
    CATALOG_SHEET_NAME,
    CONDITION_ORDER,
    FORECAST_SHEET_NAME,
    SHEET_NAME,
    SheetStore,
    load_history_frame,
    sqlite_load_history_frame,
)


st_autorefresh(interval=60 * 1000, key="buff_refresh")
st.set_page_config(page_title="BUFF163 High-Value Knife Market", layout="wide")

TRACK_KEYWORDS = ("Butterfly Knife", "Karambit")
HIGH_VALUE_MIN_PRICE = float(os.getenv("BUFF_MIN_PRICE_CNY", "5000"))


@st.cache_resource(show_spinner=False)
def get_store() -> SheetStore:
    return SheetStore(os.getenv("BUFF_SHEET_NAME", SHEET_NAME))


@st.cache_data(ttl=60, show_spinner=False)
def load_sheet_records(sheet_name: str) -> pd.DataFrame:
    try:
        worksheet = get_store().spreadsheet.worksheet(sheet_name)
        records = worksheet.get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame()
    except WorksheetNotFound:
        return pd.DataFrame(columns=CATALOG_HEADERS if sheet_name == CATALOG_SHEET_NAME else [])


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg-top: #10182a;
            --bg-main: #182235;
            --line: #2f3d56;
            --accent: #4f6fb6;
            --accent-2: #e49037;
            --text: #f5f7fb;
            --muted: #aab6ca;
            --soft: #d9dfeb;
        }
        .stApp {
            background:
                radial-gradient(circle at top right, rgba(97, 140, 220, 0.12), transparent 25%),
                linear-gradient(180deg, var(--bg-top) 0%, var(--bg-main) 26%, #101722 100%);
            color: var(--text);
        }
        .stApp, .stApp p, .stApp span, .stApp div, .stApp label, .stApp li {
            color: var(--text);
        }
        .stMarkdown, .stMarkdown p, .stMarkdown span {
            color: var(--text) !important;
        }
        .block-container {
            max-width: 1500px;
            padding-top: 0.8rem;
            padding-bottom: 2rem;
        }
        .buff-nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            padding: 0.9rem 1.2rem;
            background: rgba(9, 14, 24, 0.82);
            border: 1px solid rgba(84, 102, 136, 0.35);
            border-radius: 18px;
            margin-bottom: 1rem;
            box-shadow: 0 18px 45px rgba(0, 0, 0, 0.22);
        }
        .buff-brand {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        .buff-badge {
            width: 38px;
            height: 38px;
            border-radius: 12px;
            background: linear-gradient(135deg, #6178c4 0%, #3f5d9e 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 900;
        }
        .buff-hero {
            background: linear-gradient(135deg, rgba(25, 33, 47, 0.95) 0%, rgba(31, 37, 48, 0.96) 100%);
            border: 1px solid rgba(95, 111, 142, 0.35);
            border-radius: 26px;
            padding: 1.2rem;
            margin-bottom: 1rem;
            box-shadow: 0 24px 55px rgba(0, 0, 0, 0.24);
        }
        .buff-breadcrumb {
            color: var(--muted) !important;
            margin-bottom: 0.7rem;
            font-size: 0.9rem;
        }
        .buff-grid {
            display: grid;
            grid-template-columns: 380px minmax(0, 1fr);
            gap: 1rem;
            align-items: stretch;
        }
        .buff-image-card {
            background:
                radial-gradient(circle at center, rgba(112, 143, 208, 0.18), transparent 40%),
                linear-gradient(180deg, #2a3549 0%, #364761 100%);
            border-radius: 18px;
            min-height: 300px;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 1px solid rgba(120, 138, 173, 0.22);
            overflow: hidden;
            padding: 1rem;
        }
        .buff-knife-art {
            width: 100%;
            height: 260px;
            object-fit: contain;
            object-position: center;
            filter: drop-shadow(0 18px 24px rgba(0, 0, 0, 0.35));
        }
        .buff-title {
            font-size: 2.05rem;
            font-weight: 700;
            margin: 0 0 0.65rem 0;
            color: var(--text) !important;
        }
        .buff-submeta {
            display: flex;
            flex-wrap: wrap;
            gap: 1.2rem;
            color: var(--muted) !important;
            font-size: 0.98rem;
            margin-bottom: 1rem;
        }
        .buff-statline {
            display: flex;
            flex-wrap: wrap;
            gap: 2rem;
            align-items: baseline;
            margin-bottom: 1rem;
            padding-bottom: 0.9rem;
            border-bottom: 1px solid rgba(94, 112, 145, 0.25);
        }
        .buff-ref {
            color: var(--soft) !important;
        }
        .buff-ref strong {
            color: #ffb23f !important;
            font-size: 1.9rem;
            margin-left: 0.45rem;
        }
        .buff-panel {
            background: linear-gradient(180deg, rgba(21, 27, 37, 0.95) 0%, rgba(24, 30, 40, 0.95) 100%);
            border: 1px solid rgba(95, 111, 142, 0.35);
            border-radius: 22px;
            padding: 1rem 1rem 0.6rem 1rem;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.2);
        }
        .buff-panel-title {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-bottom: 0.85rem;
        }
        .buff-panel-title h3 {
            margin: 0;
            color: var(--text) !important;
            font-size: 1.03rem;
        }
        .buff-chip {
            color: #dce4f6 !important;
            background: rgba(79, 111, 182, 0.24);
            border: 1px solid rgba(91, 122, 191, 0.45);
            border-radius: 999px;
            padding: 0.28rem 0.7rem;
            font-size: 0.82rem;
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(26, 34, 48, 0.95) 0%, rgba(18, 24, 34, 0.95) 100%);
            border: 1px solid rgba(95, 111, 142, 0.35);
            border-radius: 18px;
            padding: 0.85rem 0.9rem;
        }
        div[data-testid="stMetricLabel"] {
            color: var(--muted) !important;
        }
        div[data-testid="stMetricValue"] {
            color: var(--text) !important;
        }
        div[data-testid="stMetricDelta"] {
            color: var(--soft) !important;
        }
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div {
            background: rgba(19, 25, 35, 0.92) !important;
            border: 1px solid rgba(95, 111, 142, 0.35) !important;
            border-radius: 14px !important;
        }
        input, textarea {
            color: var(--text) !important;
            -webkit-text-fill-color: var(--text) !important;
        }
        div[data-baseweb="select"] * {
            color: var(--text) !important;
        }
        div[role="radiogroup"] {
            gap: 0.6rem;
        }
        div[role="radiogroup"] label {
            background: rgba(79, 111, 182, 0.12);
            border: 1px solid rgba(91, 122, 191, 0.32);
            padding: 0.55rem 0.85rem;
            border-radius: 12px;
        }
        div[role="radiogroup"] label p {
            color: var(--soft) !important;
            font-weight: 600;
        }
        button[data-baseweb="tab"] {
            color: var(--muted) !important;
            background: rgba(19, 25, 35, 0.55) !important;
            border-radius: 12px 12px 0 0 !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--text) !important;
            background: rgba(79, 111, 182, 0.18) !important;
        }
        div[data-testid="stDataFrame"] {
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid rgba(95, 111, 142, 0.28);
        }
        @media (max-width: 1100px) {
            .buff-grid {
                grid-template-columns: 1fr;
            }
            .buff-image-card {
                min-height: 240px;
            }
            .buff-knife-art {
                height: 220px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_styles()

sqlite_path = os.getenv("BUFF_SQLITE_PATH", "").strip()
use_sqlite = os.getenv("BUFF_READ_SQLITE", "").strip().lower() in {"1", "true", "yes", "on"}
if use_sqlite and sqlite_path and Path(sqlite_path).exists():
    history_df = sqlite_load_history_frame(sqlite_path)
else:
    history_df = load_history_frame(get_store())
catalog_df = load_sheet_records(CATALOG_SHEET_NAME)
forecast_df = load_sheet_records(FORECAST_SHEET_NAME)

if history_df.empty:
    st.warning("No knife history exists yet. Run `python main.py` first.")
    st.stop()

history_df["Timestamp"] = pd.to_datetime(history_df["Timestamp"], errors="coerce", utc=True)
history_df["Price"] = pd.to_numeric(history_df["Price"], errors="coerce")
history_df["Listings"] = pd.to_numeric(history_df["Listings"], errors="coerce")
history_df["Buy Orders"] = pd.to_numeric(history_df.get("Buy Orders"), errors="coerce")
history_df["Reference Price"] = pd.to_numeric(history_df.get("Reference Price"), errors="coerce")
history_df["Family"] = history_df["Family"].fillna("").astype(str)
history_df["Skin Name"] = history_df["Skin Name"].fillna("").astype(str)
history_df["Condition"] = history_df["Condition"].fillna("Unknown").astype(str)
history_df["Image URL"] = history_df.get("Image URL", "").fillna("").astype(str)
history_df = history_df.dropna(subset=["Timestamp", "Family", "Skin Name", "Price"]).sort_values("Timestamp")

family_mask = history_df["Family"].str.contains("|".join(TRACK_KEYWORDS), case=False, na=False)
history_df = history_df[family_mask].copy()
latest_family_prices = (
    history_df.sort_values("Timestamp")
    .groupby("Family", as_index=False)
    .tail(1)[["Family", "Price"]]
)
high_value_families = latest_family_prices[latest_family_prices["Price"] >= HIGH_VALUE_MIN_PRICE]["Family"].tolist()
history_df = history_df[history_df["Family"].isin(high_value_families)].copy()

if history_df.empty:
    st.warning(f"No Butterfly/Karambit families above ¥{HIGH_VALUE_MIN_PRICE:,.0f} yet. Run `python main.py` to refresh.")
    st.stop()

st.markdown(
    """
    <div class="buff-nav">
      <div class="buff-brand">
        <div class="buff-badge">B</div>
        <div>BUFF163 High-Value Knife Market</div>
      </div>
      <div style="color:#aab6ca;">Butterfly + Karambit tracker (¥5,000+) with condition tabs, sell count, buy depth, and daily history.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

family_names = sorted(history_df["Family"].dropna().unique().tolist())
search_term = st.text_input(
    "Search knife family",
    placeholder="Search: Karambit Doppler, Butterfly Tiger Tooth",
    label_visibility="collapsed",
)
filtered_families = [name for name in family_names if search_term.lower() in name.lower()] if search_term else family_names
if not filtered_families:
    filtered_families = family_names

family_selected = st.selectbox("Family", filtered_families, label_visibility="collapsed")
family_df = history_df[history_df["Family"] == family_selected].copy()

condition_latest = (
    family_df.sort_values("Timestamp")
    .groupby("Condition", as_index=False)
    .tail(1)
    .assign(_sort_key=lambda frame: frame["Condition"].map(lambda value: CONDITION_ORDER.get(str(value), 50)))
    .sort_values(["_sort_key", "Condition"])
)
condition_labels = [f"{row['Condition'] or 'Unknown'}  ¥ {float(row['Price']):,.2f}" for _, row in condition_latest.iterrows()]
condition_map = dict(zip(condition_labels, condition_latest["Condition"].tolist()))

selected_condition_label = st.radio(
    "Condition",
    condition_labels,
    horizontal=True,
    label_visibility="collapsed",
)
condition_selected = condition_map[selected_condition_label]

variant_df = family_df[family_df["Condition"] == condition_selected].copy().sort_values("Timestamp")
latest = variant_df.iloc[-1]


def choose_image_url() -> str:
    for frame in (variant_df, family_df, history_df):
        candidates = frame.get("Image URL")
        if candidates is None:
            continue
        non_empty = (
            candidates.astype(str)
            .str.strip()
            .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
            .dropna()
        )
        if not non_empty.empty:
            return str(non_empty.iloc[-1])
    return ""


image_url = choose_image_url()
reference_price = float(latest["Reference Price"]) if pd.notna(latest["Reference Price"]) else float(latest["Price"])
buy_orders = int(latest["Buy Orders"]) if pd.notna(latest["Buy Orders"]) else 0
sell_stock = int(latest["Listings"]) if pd.notna(latest["Listings"]) else 0
knife_category = family_selected.split("|")[0].strip()

st.markdown(
    f"""
    <div class="buff-hero">
      <div class="buff-breadcrumb">Market &nbsp; &gt; &nbsp; {family_selected} ({condition_selected})</div>
      <div class="buff-grid">
        <div class="buff-image-card">
          {f'<img class="buff-knife-art" src="{image_url}" alt="{family_selected}">' if image_url else '<div style="color:#aab6ca;">No image available</div>'}
        </div>
        <div>
          <h1 class="buff-title">{family_selected} ({condition_selected})</h1>
          <div class="buff-submeta">
            <span>Quality | {condition_selected}</span>
            <span>Category | {knife_category}</span>
            <span>Goods ID | {str(latest.get('Goods ID') or 'N/A')}</span>
          </div>
          <div class="buff-statline">
            <div class="buff-ref">Reference price <strong>¥ {reference_price:,.2f}</strong></div>
            <div class="buff-ref">Sell stock <strong style="font-size:1.3rem;">{sell_stock}</strong></div>
            <div class="buff-ref">Buy orders <strong style="font-size:1.3rem;">{buy_orders}</strong></div>
          </div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_cols = st.columns(4)
metric_cols[0].metric("Lowest Sell", f"¥ {float(latest['Price']):,.2f}")
metric_cols[1].metric("Sell", sell_stock)
metric_cols[2].metric("Buy Orders", buy_orders)
metric_cols[3].metric("Last Update", latest["Timestamp"].strftime("%Y-%m-%d"))

daily_df = variant_df.copy()
daily_df["Day"] = daily_df["Timestamp"].dt.date
daily_df = (
    daily_df.groupby("Day", as_index=False)
    .agg(
        Price=("Price", "mean"),
        Listings=("Listings", "last"),
        BuyOrders=("Buy Orders", "last"),
    )
)
daily_df["Day"] = pd.to_datetime(daily_df["Day"])

price_chart = (
    alt.Chart(daily_df)
    .mark_line(color="#e49037", point=True, strokeWidth=3)
    .encode(
        x=alt.X("Day:T", title="Day"),
        y=alt.Y("Price:Q", title="Price (CNY)"),
        tooltip=["Day:T", "Price:Q", "Listings:Q", "BuyOrders:Q"],
    )
    .properties(height=320)
)
stock_chart = (
    alt.Chart(daily_df)
    .mark_bar(color="#5f7bd0", opacity=0.72)
    .encode(
        x=alt.X("Day:T", title="Day"),
        y=alt.Y("Listings:Q", title="Sell Stock"),
        tooltip=["Day:T", "Listings:Q", "BuyOrders:Q"],
    )
    .properties(height=180)
)

combined_chart = alt.layer(
    price_chart,
    alt.Chart(daily_df)
    .mark_bar(color="#5f7bd0", opacity=0.24)
    .encode(
        x=alt.X("Day:T", title="Day"),
        y=alt.Y(
            "Listings:Q",
            title="Sell Stock",
            axis=alt.Axis(orient="right", labelColor="#aab6ca", titleColor="#aab6ca"),
        ),
        tooltip=["Day:T", "Price:Q", "Listings:Q", "BuyOrders:Q"],
    )
    .properties(height=320),
).resolve_scale(y="independent")

left, right = st.columns((2.2, 1))

with left:
    st.markdown(
        """
        <div class="buff-panel">
          <div class="buff-panel-title">
            <h3>Price Trend</h3>
            <span class="buff-chip">Daily average sell price and day-end stock</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    chart_mode = st.radio(
        "Chart mode",
        ("Combined (Price + Stock)", "Stacked (Price above Stock)"),
        horizontal=True,
        label_visibility="collapsed",
    )
    if chart_mode.startswith("Combined"):
        st.altair_chart(combined_chart, use_container_width=True)
    else:
        st.altair_chart((price_chart & stock_chart).resolve_scale(x="shared"), use_container_width=True)

with right:
    summary = (
        variant_df[["Timestamp", "Price", "Listings", "Buy Orders"]]
        .sort_values("Timestamp", ascending=False)
        .head(8)
        .copy()
    )
    summary["Listings"] = summary["Listings"].fillna(0).astype(int)
    summary["Buy Orders"] = summary["Buy Orders"].fillna(0).astype(int)
    summary["Timestamp"] = summary["Timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    st.markdown(
        """
        <div class="buff-panel">
          <div class="buff-panel-title">
            <h3>Recent Selling Points</h3>
            <span class="buff-chip">Sell / Buy depth</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.dataframe(summary, use_container_width=True, hide_index=True)

tab1, tab2, tab3 = st.tabs(["Sell History", "Condition Catalog", "Forecast"])

with tab1:
    sell_view = variant_df[
        ["Timestamp", "Price", "Listings", "Buy Orders", "Reference Price", "Observed Orders"]
    ].sort_values("Timestamp", ascending=False)
    sell_view["Listings"] = sell_view["Listings"].fillna(0).astype(int)
    sell_view["Buy Orders"] = sell_view["Buy Orders"].fillna(0).astype(int)
    sell_view["Observed Orders"] = pd.to_numeric(sell_view["Observed Orders"], errors="coerce").fillna(0).astype(int)
    st.dataframe(sell_view, use_container_width=True, hide_index=True)

with tab2:
    if catalog_df.empty:
        st.info("Catalog sheet is empty.")
    else:
        catalog_df["Price"] = pd.to_numeric(catalog_df["Price"], errors="coerce")
        catalog_df["Listings"] = pd.to_numeric(catalog_df["Listings"], errors="coerce")
        catalog_df["Buy Orders"] = pd.to_numeric(catalog_df["Buy Orders"], errors="coerce")
        catalog_df["Condition"] = catalog_df["Condition"].fillna("Unknown").astype(str)
        family_catalog = (
            catalog_df[catalog_df["Family"] == family_selected]
            .assign(_sort_key=lambda frame: frame["Condition"].map(lambda value: CONDITION_ORDER.get(str(value), 50)))
            .sort_values(["_sort_key", "Condition"])
            .drop(columns=["_sort_key"])
        )
        family_catalog["Listings"] = family_catalog["Listings"].fillna(0).astype(int)
        family_catalog["Buy Orders"] = family_catalog["Buy Orders"].fillna(0).astype(int)
        st.dataframe(
            family_catalog[["Skin Name", "Condition", "Price", "Listings", "Buy Orders", "Goods ID"]],
            use_container_width=True,
            hide_index=True,
        )

with tab3:
    if forecast_df.empty:
        st.info("Forecast sheet is empty.")
    else:
        forecast_df["Forecast Date"] = pd.to_datetime(forecast_df["Forecast Date"], errors="coerce")
        forecast_df["Predicted Price"] = pd.to_numeric(forecast_df["Predicted Price"], errors="coerce")
        target_skin_name = f"{family_selected} ({condition_selected})"
        forecast_view = forecast_df[forecast_df["Skin Name"] == target_skin_name].dropna()
        if forecast_view.empty:
            st.info("No forecast rows for this condition.")
        else:
            forecast_chart = (
                alt.Chart(forecast_view)
                .mark_line(point=True, color="#49a078", strokeWidth=3)
                .encode(
                    x=alt.X("Forecast Date:T", title="Date"),
                    y=alt.Y("Predicted Price:Q", title="Predicted Price (CNY)"),
                    tooltip=["Forecast Date:T", "Predicted Price:Q"],
                )
                .properties(height=320)
            )
            st.altair_chart(forecast_chart, use_container_width=True)
