from __future__ import annotations

import os

import altair as alt
import pandas as pd
import streamlit as st
from gspread import WorksheetNotFound
from streamlit_autorefresh import st_autorefresh

from main import (
    ALL_CATALOG_HEADERS,
    ALL_CATALOG_SHEET_NAME,
    BuffPriceClient,
    CATALOG_HEADERS,
    CATALOG_SHEET_NAME,
    CONDITION_ORDER,
    DEFAULT_KNIFE_CATEGORIES,
    FORECAST_SHEET_NAME,
    DEFAULT_TRACK_KEYWORDS,
    csgotrader_snapshots,
    SHEET_NAME,
    SheetStore,
    load_history_frame,
    sqlite_load_history_frame,
)
from app_data_utils import (
    choose_image_url,
    filter_high_value_families,
    load_app_frames,
    prepare_history_frame,
)


REFRESH_SECONDS = int(os.getenv("BUFF_UI_REFRESH_SEC", "900"))
CACHE_TTL_SECONDS = int(os.getenv("BUFF_UI_CACHE_TTL_SEC", "300"))
st_autorefresh(interval=max(30, REFRESH_SECONDS) * 1000, key="buff_refresh")
st.set_page_config(page_title="CS2 Skin Market", layout="wide")

TRACK_KEYWORDS = tuple(DEFAULT_TRACK_KEYWORDS)
HIGH_VALUE_MIN_PRICE = float(os.getenv("BUFF_MIN_PRICE_CNY", "0"))


def fallback_history_frame() -> pd.DataFrame:
    timestamp = pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    snapshots = csgotrader_snapshots(list(TRACK_KEYWORDS), HIGH_VALUE_MIN_PRICE)
    return pd.DataFrame(
        [
            {
                "Timestamp": timestamp,
                "Goods ID": snapshot.goods_id,
                "Family": snapshot.family,
                "Knife Type": snapshot.knife_type,
                "Skin Name": snapshot.skin_name,
                "Condition": snapshot.condition,
                "Price": snapshot.price,
                "Listings": snapshot.listings,
                "Buy Orders": snapshot.buy_orders,
                "Reference Price": snapshot.reference_price,
                "Image URL": snapshot.image_url,
                "Observed Orders": snapshot.observed_orders,
                "Source": "Fallback",
            }
            for snapshot in snapshots
        ]
    )


def merge_fallback_history(history: pd.DataFrame) -> pd.DataFrame:
    if os.getenv("BUFF_APP_FALLBACK_CSGOTRADER", "1").strip().lower() not in {"1", "true", "yes", "on"}:
        return history
    try:
        fallback = fallback_history_frame()
    except Exception:
        return history
    if history.empty:
        return fallback
    fallback = fallback.copy()
    history = history.copy()
    if {"Family", "Condition", "Listings", "Buy Orders"}.issubset(history.columns):
        hist_stats = (
            history.assign(Timestamp=pd.to_datetime(history.get("Timestamp"), errors="coerce", utc=True))
            .sort_values("Timestamp")
            .groupby(["Family", "Condition"], as_index=False)
            .tail(1)[["Family", "Condition", "Listings", "Buy Orders"]]
            .rename(columns={"Listings": "_Hist Listings", "Buy Orders": "_Hist Buy Orders"})
        )
        fallback = fallback.merge(hist_stats, on=["Family", "Condition"], how="left")
        fallback["Listings"] = fallback["Listings"].where(fallback["Listings"].fillna(0) > 0, fallback["_Hist Listings"])
        fallback["Buy Orders"] = fallback["Buy Orders"].where(
            fallback["Buy Orders"].fillna(0) > 0, fallback["_Hist Buy Orders"]
        )
        fallback = fallback.drop(columns=["_Hist Listings", "_Hist Buy Orders"])
    fallback["_Fallback Current"] = 1
    history["_Fallback Current"] = 0
    merged = pd.concat([history, fallback], ignore_index=True)
    merged["Timestamp"] = pd.to_datetime(merged["Timestamp"], errors="coerce", utc=True)
    return merged.sort_values(["_Fallback Current", "Timestamp"]).drop(columns=["_Fallback Current"])


def base_knife_type(value: object) -> str:
    return str(value or "").replace("StatTrak™ ", "", 1).strip()


def knife_tile_image(frame: pd.DataFrame) -> str:
    priority = (
        "Doppler",
        "Gamma Doppler",
        "Marble Fade",
        "Fade",
        "Tiger Tooth",
        "Slaughter",
        "Crimson Web",
        "Case Hardened",
    )
    for finish in priority:
        image_url = choose_image_url(frame[frame["Family"].str.contains(finish, case=False, na=False)])
        if image_url:
            return image_url
    return choose_image_url(frame.sort_values("Timestamp"))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def live_buff_listing(family: str, condition: str, knife_type: str) -> dict[str, object]:
    if not os.getenv("BUFF_COOKIE"):
        return {}
    category = DEFAULT_KNIFE_CATEGORIES.get(base_knife_type(knife_type))
    try:
        snapshots = BuffPriceClient(timeout=15).discover_snapshots_from_market(
            keyword=family,
            category=category,
            min_price=0,
            max_pages=1,
        )
    except Exception:
        return {}
    for snapshot in snapshots:
        if snapshot.family == family and snapshot.condition == condition:
            return {
                "goods_id": snapshot.goods_id,
                "listings": snapshot.listings,
                "buy_orders": snapshot.buy_orders,
                "reference_price": snapshot.reference_price,
                "image_url": snapshot.image_url,
            }
    return {}


@st.cache_resource(show_spinner=False)
def get_store() -> SheetStore:
    return SheetStore(os.getenv("BUFF_SHEET_NAME", SHEET_NAME))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_sheet_records(sheet_name: str) -> pd.DataFrame:
    try:
        worksheet = get_store().spreadsheet.worksheet(sheet_name)
        records = worksheet.get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame()
    except WorksheetNotFound:
        return pd.DataFrame(columns=CATALOG_HEADERS if sheet_name == CATALOG_SHEET_NAME else [])


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_history_records() -> pd.DataFrame:
    return load_history_frame(get_store())


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg-top: #0d1422;
            --bg-main: #172233;
            --line: #2f3d56;
            --accent: #5076c8;
            --accent-2: #f0a23b;
            --text: #f5f7fb;
            --muted: #aab6ca;
            --soft: #d9dfeb;
            --panel: rgba(18, 25, 37, 0.88);
        }
        .stApp {
            background:
                radial-gradient(circle at 85% 0%, rgba(240, 162, 59, 0.13), transparent 24rem),
                radial-gradient(circle at 10% 12%, rgba(80, 118, 200, 0.16), transparent 26rem),
                linear-gradient(180deg, var(--bg-top) 0%, var(--bg-main) 30%, #0f1622 100%);
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
            padding: 1rem 1.15rem;
            background: linear-gradient(135deg, rgba(11, 17, 28, 0.92), rgba(25, 34, 49, 0.86));
            border: 1px solid rgba(126, 146, 184, 0.28);
            border-radius: 8px;
            margin-bottom: 1.1rem;
            box-shadow: 0 18px 45px rgba(0, 0, 0, 0.26);
            backdrop-filter: blur(10px);
        }
        .buff-brand {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            font-weight: 800;
            font-size: 1.05rem;
        }
        .buff-badge {
            width: 42px;
            height: 42px;
            border-radius: 8px;
            background: linear-gradient(135deg, #f0a23b 0%, #5076c8 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 900;
            box-shadow: 0 10px 24px rgba(240, 162, 59, 0.22);
        }
        .buff-nav-subtitle {
            color: #aab6ca !important;
            font-size: 0.92rem;
        }
        .buff-picker-title {
            color: var(--muted) !important;
            font-size: 0.86rem;
            font-weight: 700;
            margin: 0.8rem 0 0.55rem;
            text-transform: uppercase;
        }
        .buff-knife-tile {
            height: 104px;
            border: 1px solid rgba(129, 149, 184, 0.28);
            border-radius: 8px;
            background:
                radial-gradient(circle at center, rgba(240, 162, 59, 0.13), transparent 50%),
                linear-gradient(180deg, rgba(32, 43, 61, 0.95), rgba(14, 20, 31, 0.98));
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0.5rem;
            margin-bottom: 0.35rem;
            overflow: hidden;
        }
        .buff-knife-tile img {
            width: 100%;
            height: 84px;
            object-fit: contain;
            filter: drop-shadow(0 16px 16px rgba(0, 0, 0, 0.46));
        }
        .buff-knife-tile-active {
            border-color: rgba(240, 162, 59, 0.9);
            background:
                radial-gradient(circle at center, rgba(240, 162, 59, 0.24), transparent 52%),
                linear-gradient(180deg, rgba(47, 59, 79, 0.98), rgba(18, 25, 37, 0.99));
            box-shadow: inset 0 0 0 1px rgba(240, 162, 59, 0.18), 0 12px 26px rgba(0, 0, 0, 0.22);
        }
        .buff-selected-label {
            color: #f6b35d !important;
            font-size: 0.78rem;
            font-weight: 800;
            min-height: 1rem;
            margin-bottom: 0.15rem;
            text-align: center;
        }
        .buff-knife-empty {
            width: 100%;
            height: 72px;
            background: rgba(120, 138, 173, 0.08);
            border-radius: 6px;
        }
        div[data-testid="stButton"] > button {
            background: rgba(245, 247, 251, 0.075) !important;
            border: 1px solid rgba(170, 182, 202, 0.28) !important;
            color: #f5f7fb !important;
            border-radius: 8px !important;
            min-height: 2.6rem;
            font-weight: 700 !important;
            transition: border-color 120ms ease, background 120ms ease, transform 120ms ease;
        }
        div[data-testid="stButton"] > button p,
        div[data-testid="stButton"] > button span {
            color: #f5f7fb !important;
        }
        div[data-testid="stButton"] > button:hover {
            background: rgba(240, 162, 59, 0.2) !important;
            border-color: rgba(240, 162, 59, 0.78) !important;
            color: #ffffff !important;
            transform: translateY(-1px);
        }
        div[data-testid="stButton"] > button:focus {
            box-shadow: 0 0 0 2px rgba(228, 144, 55, 0.35) !important;
        }
        .buff-hero {
            background:
                radial-gradient(circle at 20% 8%, rgba(240, 162, 59, 0.13), transparent 18rem),
                linear-gradient(135deg, rgba(18, 25, 37, 0.96) 0%, rgba(28, 38, 55, 0.96) 100%);
            border: 1px solid rgba(126, 146, 184, 0.32);
            border-radius: 8px;
            padding: 1.25rem;
            margin-bottom: 1rem;
            box-shadow: 0 28px 65px rgba(0, 0, 0, 0.28);
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
                radial-gradient(circle at center, rgba(240, 162, 59, 0.14), transparent 36%),
                radial-gradient(circle at 70% 18%, rgba(112, 143, 208, 0.2), transparent 42%),
                linear-gradient(180deg, #253247 0%, #344761 100%);
            border-radius: 8px;
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
            font-size: 2.2rem;
            font-weight: 700;
            margin: 0 0 0.65rem 0;
            color: var(--text) !important;
            line-height: 1.1;
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
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.75rem;
            margin-top: 1.1rem;
        }
        .buff-ref {
            color: var(--soft) !important;
            background: rgba(8, 13, 22, 0.32);
            border: 1px solid rgba(126, 146, 184, 0.22);
            border-radius: 8px;
            padding: 0.78rem 0.85rem;
        }
        .buff-ref strong {
            color: #ffb23f !important;
            display: block;
            font-size: 1.45rem;
            margin: 0.15rem 0 0;
            line-height: 1.15;
        }
        .buff-panel {
            background: linear-gradient(180deg, rgba(21, 27, 37, 0.94) 0%, rgba(18, 25, 35, 0.94) 100%);
            border: 1px solid rgba(95, 111, 142, 0.35);
            border-radius: 8px;
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
            border-radius: 8px;
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
            border-radius: 8px !important;
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
            border-radius: 8px;
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
            .buff-statline {
                grid-template-columns: 1fr;
            }
            .buff-image-card {
                min-height: 240px;
            }
            .buff-knife-art {
                height: 220px;
            }
            .buff-nav {
                align-items: flex-start;
                flex-direction: column;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_styles()

sqlite_path = os.getenv("BUFF_SQLITE_PATH", "").strip()
use_sqlite = os.getenv("BUFF_READ_SQLITE", "").strip().lower() in {"1", "true", "yes", "on"}
history_df, catalog_df, all_catalog_df, forecast_df, startup_error = load_app_frames(
    use_sqlite=use_sqlite,
    sqlite_path=sqlite_path,
    load_sqlite_history=sqlite_load_history_frame,
    load_sheet_history=load_history_records,
    load_sheet_records=load_sheet_records,
    catalog_sheet_name=CATALOG_SHEET_NAME,
    all_catalog_sheet_name=ALL_CATALOG_SHEET_NAME,
    forecast_sheet_name=FORECAST_SHEET_NAME,
)

if startup_error is not None:
    try:
        history_df = fallback_history_frame()
        startup_error = None
    except Exception as fallback_error:
        st.error("Cannot load data source. Check Google Sheet credentials or enable SQLite mode.")
        st.code(str(startup_error))
        st.info("Set `GSHEET_CREDS_JSON`/`credentials.json`, or set `BUFF_READ_SQLITE=1` with `BUFF_SQLITE_PATH`.")
        st.code(f"Fallback failed: {fallback_error}")
        st.stop()
        raise SystemExit(0)

if history_df.empty:
    history_df = fallback_history_frame()

history_df = merge_fallback_history(history_df)

required_cols = {"Timestamp", "Price", "Listings", "Family", "Skin Name", "Condition"}
if not required_cols.issubset(set(history_df.columns)):
    st.error("History data is missing required columns. Run `python main.py --migrate-only` once.")
    st.code(f"Missing columns: {sorted(required_cols - set(history_df.columns))}")
    st.stop()
    raise SystemExit(0)

history_df = prepare_history_frame(history_df)
history_df = filter_high_value_families(history_df, TRACK_KEYWORDS, HIGH_VALUE_MIN_PRICE)

if history_df.empty:
    st.warning(f"No knife families above {HIGH_VALUE_MIN_PRICE:,.0f} CNY yet. Run `python main.py` to refresh.")
    st.stop()
    raise SystemExit(0)

st.markdown(
    f"""
    <div class="buff-nav">
      <div class="buff-brand">
        <div class="buff-badge">B</div>
        <div>CS2 Skin Market</div>
      </div>
      <div class="buff-nav-subtitle">Live BUFF listings {'enabled' if os.getenv('BUFF_COOKIE') else 'waiting for cookie'} · Auto refresh every {max(30, REFRESH_SECONDS) // 60} min</div>
    </div>
    """,
    unsafe_allow_html=True,
)

family_names = sorted(history_df["Family"].dropna().unique().tolist())

history_df["_Base Knife"] = history_df.get("Knife Type", history_df["Family"].str.split("|").str[0]).map(base_knife_type)
knife_counts = history_df.groupby("_Base Knife")["Family"].nunique().sort_index()
knife_types = [knife for knife in DEFAULT_TRACK_KEYWORDS if knife in knife_counts.index]
if "selected_knife_type" not in st.session_state or st.session_state["selected_knife_type"] not in knife_types:
    st.session_state["selected_knife_type"] = knife_types[0] if knife_types else ""

st.markdown('<div class="buff-picker-title">Choose knife type</div>', unsafe_allow_html=True)
for row_start in range(0, len(knife_types), 5):
    cols = st.columns(5)
    for col, knife_type in zip(cols, knife_types[row_start:row_start + 5]):
        knife_df = history_df[history_df["_Base Knife"] == knife_type].copy()
        image_url = knife_tile_image(knife_df.sort_values("Timestamp"))
        active_class = " buff-knife-tile-active" if st.session_state["selected_knife_type"] == knife_type else ""
        with col:
            st.markdown(
                f"""
                <div class="buff-selected-label">{'Selected' if active_class else '&nbsp;'}</div>
                <div class="buff-knife-tile{active_class}">
                  {f'<img src="{image_url}" alt="{knife_type}">' if image_url else '<div class="buff-knife-empty"></div>'}
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"{knife_type} ({int(knife_counts[knife_type])})", key=f"knife_{knife_type}", width="stretch"):
                st.session_state["selected_knife_type"] = knife_type

selected_knife_type = st.session_state["selected_knife_type"]
scoped_names = sorted(history_df.loc[history_df["_Base Knife"] == selected_knife_type, "Family"].dropna().unique().tolist())
filtered_families = scoped_names
if not filtered_families:
    filtered_families = scoped_names or family_names

family_selected = st.selectbox(
    "Family",
    filtered_families,
    label_visibility="collapsed",
    placeholder=f"{selected_knife_type} skins",
)
family_df = history_df[history_df["Family"] == family_selected].copy()

condition_latest = (
    family_df.sort_values("Timestamp")
    .assign(_source_key=lambda frame: frame.get("Source", pd.Series("", index=frame.index)).eq("Fallback").astype(int))
    .sort_values(["_source_key", "Timestamp"])
    .groupby("Condition", as_index=False)
    .tail(1)
    .assign(_sort_key=lambda frame: frame["Condition"].map(lambda value: CONDITION_ORDER.get(str(value), 50)))
    .sort_values(["_sort_key", "Condition"])
)
condition_labels = [f"{row['Condition'] or 'Unknown'}  {float(row['Price']):,.2f} CNY" for _, row in condition_latest.iterrows()]
condition_map = dict(zip(condition_labels, condition_latest["Condition"].tolist()))

selected_condition_label = st.radio(
    "Condition",
    condition_labels,
    horizontal=True,
    label_visibility="collapsed",
)
condition_selected = condition_map[selected_condition_label]

variant_df = (
    family_df[family_df["Condition"] == condition_selected]
    .copy()
    .assign(_source_key=lambda frame: frame.get("Source", pd.Series("", index=frame.index)).eq("Fallback").astype(int))
    .sort_values(["_source_key", "Timestamp"])
)
latest = variant_df.iloc[-1]
image_url = choose_image_url(variant_df)
reference_price = float(latest["Reference Price"]) if pd.notna(latest["Reference Price"]) else float(latest["Price"])
buy_orders = int(latest["Buy Orders"]) if pd.notna(latest["Buy Orders"]) else 0
sell_stock = int(latest["Listings"]) if pd.notna(latest["Listings"]) else 0
knife_category = family_selected.split("|")[0].strip()
goods_id = str(latest.get("Goods ID") or "N/A")
if os.getenv("BUFF_APP_LIVE_LISTINGS", "1").strip().lower() in {"1", "true", "yes", "on"}:
    live_listing = live_buff_listing(family_selected, condition_selected, knife_category)
    if live_listing:
        sell_stock = int(live_listing.get("listings") or 0)
        buy_orders = int(live_listing.get("buy_orders") or 0)
        goods_id = str(live_listing.get("goods_id") or goods_id)
        if live_listing.get("reference_price") is not None:
            reference_price = float(live_listing["reference_price"])
        image_url = str(live_listing.get("image_url") or image_url)
listing_source = "BUFF" if sell_stock > 0 else "BUFF unavailable"

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
            <span>Goods ID | {goods_id}</span>
          </div>
          <div class="buff-statline">
            <div class="buff-ref">Reference price <strong>{reference_price:,.2f} CNY</strong></div>
            <div class="buff-ref">Listings <strong style="font-size:1.3rem;">{sell_stock if sell_stock else 'N/A'}</strong><br><span>{listing_source}</span></div>
            <div class="buff-ref">Buy orders <strong style="font-size:1.3rem;">{buy_orders}</strong></div>
          </div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_cols = st.columns(4)
metric_cols[0].metric("Lowest Sell", f"{float(latest['Price']):,.2f} CNY")
metric_cols[1].metric("Listings", sell_stock if sell_stock else "N/A", help=f"Source: {listing_source}")
metric_cols[2].metric("Buy Orders", buy_orders)
metric_cols[3].metric("Last Update", latest["Timestamp"].strftime("%Y-%m-%d"))
if listing_source == "BUFF unavailable":
    st.caption("BUFF listings are unavailable for this fallback-imported skin. Set `BUFF_COOKIE` and run direct BUFF refresh to fill listings.")

daily_df = variant_df.copy()
if "Listings" in daily_df.columns:
    daily_df.loc[daily_df["Listings"].fillna(0) <= 0, "Listings"] = pd.NA
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
    .mark_line(color="#5f7bd0", point=True, strokeWidth=2.5)
    .encode(
        x=alt.X("Day:T", title="Day"),
        y=alt.Y("Listings:Q", title="Sell Stock"),
        tooltip=["Day:T", "Price:Q", "Listings:Q", "BuyOrders:Q"],
    )
    .properties(height=180)
)

combined_chart = alt.layer(
    price_chart,
    alt.Chart(daily_df)
    .mark_line(color="#5f7bd0", point=True, strokeWidth=2.5, opacity=0.85)
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
        st.altair_chart(combined_chart, width="stretch")
    else:
        st.altair_chart((price_chart & stock_chart).resolve_scale(x="shared"), width="stretch")

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
    st.dataframe(summary, width="stretch", hide_index=True)

tab1, tab2, tab3, tab4 = st.tabs(["Sell History", "Condition Catalog", "Forecast", "Full Catalog"])

with tab1:
    sell_view = variant_df[
        ["Timestamp", "Price", "Listings", "Buy Orders", "Reference Price", "Observed Orders"]
    ].sort_values("Timestamp", ascending=False)
    sell_view["Listings"] = sell_view["Listings"].fillna(0).astype(int)
    sell_view["Buy Orders"] = sell_view["Buy Orders"].fillna(0).astype(int)
    sell_view["Observed Orders"] = pd.to_numeric(sell_view["Observed Orders"], errors="coerce").fillna(0).astype(int)
    st.dataframe(sell_view, width="stretch", hide_index=True)

with tab2:
    if catalog_df.empty:
        catalog_df = load_sheet_records(CATALOG_SHEET_NAME)
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
            width="stretch",
            hide_index=True,
        )

with tab3:
    if forecast_df.empty:
        forecast_df = load_sheet_records(FORECAST_SHEET_NAME)
    if forecast_df.empty:
        st.info("Forecast sheet is empty.")
    else:
        forecast_df["Forecast Date"] = pd.to_datetime(forecast_df["Forecast Date"], errors="coerce")
        forecast_df["Predicted Price"] = pd.to_numeric(forecast_df.get("Predicted Price"), errors="coerce")
        if "Predicted Listings" in forecast_df.columns:
            forecast_df["Predicted Listings"] = pd.to_numeric(forecast_df.get("Predicted Listings"), errors="coerce")
        target_skin_name = f"{family_selected} ({condition_selected})"
        forecast_view = forecast_df[forecast_df["Skin Name"] == target_skin_name].dropna()
        if forecast_view.empty:
            st.info("No forecast rows for this condition.")
        else:
            if "Predicted Listings" in forecast_view.columns:
                price_forecast = (
                    alt.Chart(forecast_view)
                    .mark_line(point=True, color="#49a078", strokeWidth=3)
                    .encode(
                        x=alt.X("Forecast Date:T", title="Date"),
                        y=alt.Y("Predicted Price:Q", title="Predicted Price (CNY)"),
                        tooltip=["Forecast Date:T", "Predicted Price:Q", "Predicted Listings:Q", "Model:N"],
                    )
                    .properties(height=320)
                )
                listings_forecast = (
                    alt.Chart(forecast_view)
                    .mark_line(color="#5f7bd0", point=True, strokeWidth=2.5, opacity=0.85)
                    .encode(
                        x=alt.X("Forecast Date:T", title="Date"),
                        y=alt.Y(
                            "Predicted Listings:Q",
                            title="Predicted Sell Stock",
                            axis=alt.Axis(orient="right"),
                        ),
                        tooltip=["Forecast Date:T", "Predicted Price:Q", "Predicted Listings:Q", "Model:N"],
                    )
                    .properties(height=320)
                )
                st.altair_chart(
                    alt.layer(price_forecast, listings_forecast).resolve_scale(y="independent"),
                    width="stretch",
                )
                show_cols = [col for col in ("Forecast Date", "Predicted Price", "Predicted Listings", "Model") if col in forecast_view.columns]
                st.dataframe(
                    forecast_view[show_cols].sort_values("Forecast Date"),
                    width="stretch",
                    hide_index=True,
                )
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
                st.altair_chart(forecast_chart, width="stretch")

with tab4:
    if "load_full_catalog" not in st.session_state:
        st.session_state["load_full_catalog"] = False
    col_load, col_hint = st.columns((1, 3))
    with col_load:
        if st.button("Load Full Catalog"):
            st.session_state["load_full_catalog"] = True
    with col_hint:
        st.caption("This sheet can be large; loading on demand keeps the app fast.")

    if st.session_state["load_full_catalog"] and all_catalog_df.empty:
        all_catalog_df = load_sheet_records(ALL_CATALOG_SHEET_NAME)

    if all_catalog_df.empty:
        st.info("Full catalog not loaded yet. Click 'Load Full Catalog'.")
    else:
        for col in ("Price", "Listings", "Buy Orders", "Reference Price"):
            if col in all_catalog_df.columns:
                all_catalog_df[col] = pd.to_numeric(all_catalog_df[col], errors="coerce")
        all_catalog_df["Family"] = all_catalog_df.get("Family", "").fillna("").astype(str)
        scoped = all_catalog_df[all_catalog_df["Family"] == family_selected].copy() if family_selected else all_catalog_df.copy()
        cols = [c for c in ("Timestamp", "Skin Name", "Condition", "Price", "Listings", "Buy Orders", "Reference Price", "Goods ID", "Goods URL", "Image URL") if c in scoped.columns]
        st.dataframe(scoped[cols].sort_values(["Price"], ascending=False, na_position="last"), width="stretch", hide_index=True)
