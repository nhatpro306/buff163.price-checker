from __future__ import annotations

import os
from typing import Any, cast

import altair as alt
import pandas as pd
import streamlit as st
from gspread import WorksheetNotFound
from streamlit_autorefresh import st_autorefresh

from app_data_utils import (
    choose_image_url,
    filter_fallback_overrides_same_day,
    filter_high_value_families,
    load_app_frames,
    prepare_history_frame,
)
from main import (
    ALL_CATALOG_SHEET_NAME,
    CATALOG_HEADERS,
    CATALOG_SHEET_NAME,
    CONDITION_ORDER,
    DEFAULT_KNIFE_CATEGORIES,
    DEFAULT_TRACK_KEYWORDS,
    FORECAST_SHEET_NAME,
    SHEET_NAME,
    BuffPriceClient,
    SheetStore,
    csgotrader_snapshots,
    load_history_frame,
    sqlite_load_history_frame,
)
from market_utils import debug_log, env_flag

REFRESH_SECONDS = int(os.getenv("BUFF_UI_REFRESH_SEC", "900"))
CACHE_TTL_SECONDS = int(os.getenv("BUFF_UI_CACHE_TTL_SEC", "300"))
st.set_page_config(page_title="BUFF163 Price Analytics", page_icon="📈", layout="wide")
st_autorefresh(interval=max(30, REFRESH_SECONDS) * 1000, key="buff_refresh")

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
    if os.getenv("BUFF_APP_FALLBACK_CSGOTRADER", "1").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return history
    try:
        fallback = fallback_history_frame()
    except Exception:
        return history
    if history.empty:
        debug_log(f"ui fallback_merge history=0 fallback={len(fallback)} final={len(fallback)}")
        return fallback
    fallback = fallback.copy()
    history = history.copy()
    if {"Family", "Condition", "Listings", "Buy Orders"}.issubset(history.columns):
        hist_stats = (
            history.assign(
                Timestamp=pd.to_datetime(history.get("Timestamp"), errors="coerce", utc=True)
            )
            .sort_values("Timestamp")
            .groupby(["Family", "Condition"], as_index=False)
            .tail(1)[["Family", "Condition", "Listings", "Buy Orders"]]
            .rename(columns={"Listings": "_Hist Listings", "Buy Orders": "_Hist Buy Orders"})
        )
        fallback = fallback.merge(hist_stats, on=["Family", "Condition"], how="left")
        fallback["Listings"] = fallback["Listings"].where(
            fallback["Listings"].fillna(0) > 0, fallback["_Hist Listings"]
        )
        fallback["Buy Orders"] = fallback["Buy Orders"].where(
            fallback["Buy Orders"].fillna(0) > 0, fallback["_Hist Buy Orders"]
        )
        fallback = fallback.drop(columns=["_Hist Listings", "_Hist Buy Orders"])
    fallback_before_filter = len(fallback)
    fallback = filter_fallback_overrides_same_day(history, fallback)
    fallback["_Fallback Current"] = 1
    history["_Fallback Current"] = 0
    merged = pd.concat([history, fallback], ignore_index=True)
    merged["Timestamp"] = pd.to_datetime(merged["Timestamp"], errors="coerce", utc=True)
    result = merged.sort_values(["_Fallback Current", "Timestamp"]).drop(
        columns=["_Fallback Current"]
    )
    debug_log(
        "ui fallback_merge "
        f"history={len(history)} fallback_raw={fallback_before_filter} "
        f"fallback_kept={len(fallback)} final={len(result)}"
    )
    return result


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
        image_url = choose_image_url(
            frame[frame["Family"].str.contains(finish, case=False, na=False)]
        )
        if image_url:
            return image_url
    return choose_image_url(frame.sort_values("Timestamp"))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def live_buff_listing(family: str, condition: str, knife_type: str) -> dict[str, object]:
    if not os.getenv("BUFF_COOKIE"):
        return {
            "status": "cookie missing",
            "checked_at": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
    category = DEFAULT_KNIFE_CATEGORIES.get(base_knife_type(knife_type))
    try:
        client = BuffPriceClient(timeout=15)
        snapshots = client.discover_snapshots_from_market(
            keyword=family, category=category, min_price=0, max_pages=1
        )
        if not snapshots:
            skin_finish = family.split("|", 1)[-1].strip() if "|" in family else family
            snapshots = client.discover_snapshots_from_market(
                keyword=skin_finish,
                category=category,
                min_price=0,
                max_pages=1,
            )
    except Exception as exc:
        return {
            "status": f"error: {exc.__class__.__name__}",
            "checked_at": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
    for snapshot in snapshots:
        if snapshot.family == family and snapshot.condition == condition:
            return {
                "status": "live",
                "checked_at": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                "goods_id": snapshot.goods_id,
                "listings": snapshot.listings,
                "buy_orders": snapshot.buy_orders,
                "reference_price": snapshot.reference_price,
                "image_url": snapshot.image_url,
            }
    return {
        "status": "no matching listing",
        "checked_at": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


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


def money(value: object) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    return "N/A" if pd.isna(numeric) else f"{float(numeric):,.2f} CNY"


def whole(value: object) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    return "N/A" if pd.isna(numeric) else f"{int(numeric):,}"


def section_title(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"""
        <div class="buff-section-title">
          <h3>{title}</h3>
          {f'<span>{subtitle}</span>' if subtitle else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(title: str, detail: str) -> None:
    st.markdown(
        f"""
        <div class="buff-empty">
          <strong>{title}</strong>
          <span>{detail}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def price_delta(frame: pd.DataFrame) -> tuple[float | None, float | None]:
    prices = pd.to_numeric(frame.get("Price"), errors="coerce").dropna()
    if len(prices) < 2:
        return None, None
    first = float(prices.iloc[0])
    last = float(prices.iloc[-1])
    if first == 0:
        return last - first, None
    return last - first, ((last - first) / first) * 100


def render_kpis(frame: pd.DataFrame, sell_stock: int, buy_orders: int, reference_price: float) -> None:
    prices = pd.to_numeric(frame.get("Price"), errors="coerce").dropna()
    latest_price = prices.iloc[-1] if not prices.empty else pd.NA
    change_abs, change_pct = price_delta(frame)
    delta = None if change_abs is None else f"{change_abs:+,.2f} CNY"
    pct_label = "N/A" if change_pct is None else f"{change_pct:+.2f}%"

    rows = [
        ("Latest Price", money(latest_price), delta),
        ("Average Price", money(prices.mean() if not prices.empty else pd.NA), None),
        ("Highest Price", money(prices.max() if not prices.empty else pd.NA), None),
        ("Lowest Price", money(prices.min() if not prices.empty else pd.NA), None),
        ("Price Change %", pct_label, None),
        ("Listings Count", whole(sell_stock), None),
        ("Buy Orders", whole(buy_orders), None),
        ("Reference Price", money(reference_price), None),
    ]
    for start in (0, 4):
        cols = st.columns(4)
        for col, (label, value, item_delta) in zip(cols, rows[start:start + 4]):
            col.metric(label, value, delta=item_delta)


def format_market_table(frame: pd.DataFrame) -> pd.io.formats.style.Styler:
    visible = frame.copy()
    for col in ("Price", "Reference Price", "Predicted Price"):
        if col in visible.columns:
            visible[col] = pd.to_numeric(visible[col], errors="coerce")
    for col in ("Listings", "Buy Orders", "Observed Orders", "Predicted Listings"):
        if col in visible.columns:
            visible[col] = pd.to_numeric(visible[col], errors="coerce")
    formatters = {
        col: "{:,.2f} CNY"
        for col in ("Price", "Reference Price", "Predicted Price")
        if col in visible.columns
    }
    formatters.update(
        {
            col: "{:,.0f}"
            for col in ("Listings", "Buy Orders", "Observed Orders", "Predicted Listings")
            if col in visible.columns
        }
    )
    return visible.style.format(formatters, na_rep="N/A")


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
        .stApp {
            background: #0b111b;
        }
        .block-container {
            padding-top: 1rem;
        }
        section[data-testid="stSidebar"] {
            background: #0e1623;
            border-right: 1px solid rgba(132, 150, 178, 0.18);
        }
        section[data-testid="stSidebar"] > div {
            padding-top: 1.1rem;
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] label p {
            color: #e9eef8 !important;
        }
        .buff-sidebar-head {
            border: 1px solid rgba(132, 150, 178, 0.22);
            background: rgba(18, 27, 40, 0.96);
            border-radius: 12px;
            padding: 0.9rem;
            margin-bottom: 1rem;
        }
        .buff-sidebar-head strong {
            display: block;
            color: #f5f7fb !important;
            font-size: 1rem;
        }
        .buff-sidebar-head span {
            color: #9eabc0 !important;
            font-size: 0.82rem;
        }
        .buff-header {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: flex-start;
            background: #111a28;
            border: 1px solid rgba(132, 150, 178, 0.22);
            border-radius: 14px;
            padding: 1.05rem 1.15rem;
            margin-bottom: 1rem;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.24);
        }
        .buff-header h1 {
            margin: 0;
            color: #f5f7fb !important;
            font-size: clamp(1.55rem, 2vw, 2.25rem);
            letter-spacing: 0;
        }
        .buff-header p {
            color: #9eabc0 !important;
            margin: 0.35rem 0 0;
        }
        .buff-status {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            border: 1px solid rgba(73, 160, 120, 0.45);
            background: rgba(73, 160, 120, 0.12);
            color: #9be7c4 !important;
            border-radius: 999px;
            padding: 0.35rem 0.65rem;
            white-space: nowrap;
            font-size: 0.82rem;
            font-weight: 700;
        }
        .buff-status-warn {
            border-color: rgba(240, 162, 59, 0.48);
            background: rgba(240, 162, 59, 0.13);
            color: #ffd08a !important;
        }
        .buff-section-title {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin: 1.15rem 0 0.55rem;
        }
        .buff-section-title h3 {
            margin: 0;
            font-size: 1.05rem;
            color: #f5f7fb !important;
        }
        .buff-section-title span {
            color: #9eabc0 !important;
            font-size: 0.86rem;
        }
        .buff-empty {
            border: 1px solid rgba(240, 162, 59, 0.35);
            background: rgba(240, 162, 59, 0.08);
            border-radius: 12px;
            padding: 1rem;
            margin: 0.75rem 0;
        }
        .buff-empty strong {
            display: block;
            color: #ffe0ad !important;
            margin-bottom: 0.25rem;
        }
        .buff-empty span {
            color: #c6cfdd !important;
        }
        div[data-testid="stMetric"] {
            border-radius: 14px;
            background: #111a28;
            border: 1px solid rgba(132, 150, 178, 0.2);
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
            transition: transform 120ms ease, border-color 120ms ease;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-1px);
            border-color: rgba(240, 162, 59, 0.42);
        }
        div[data-testid="stMetricValue"] {
            font-size: clamp(1.35rem, 1.8vw, 1.85rem) !important;
            line-height: 1.12 !important;
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }
        button[data-baseweb="tab"] {
            border-radius: 10px !important;
            margin-right: 0.35rem !important;
        }
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 0.25rem;
            border-bottom: 1px solid rgba(132, 150, 178, 0.18);
        }
        div[data-testid="stDataFrame"] {
            border-radius: 12px;
            background: #111a28;
            border-color: rgba(132, 150, 178, 0.2);
        }
        div[data-testid="stSpinner"] {
            color: #f5f7fb !important;
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
            .buff-header {
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
debug_log(
    "ui loaded "
    f"history_rows={len(history_df)} catalog_rows={len(catalog_df)} "
    f"all_catalog_rows={len(all_catalog_df)} forecast_rows={len(forecast_df)} "
    f"source={'sqlite' if use_sqlite and sqlite_path else 'sheets'}"
)

if startup_error is not None:
    try:
        history_df = fallback_history_frame()
        startup_error = None
    except Exception as fallback_error:
        st.error("Cannot load data source. Check Google Sheet credentials or enable SQLite mode.")
        st.code(str(startup_error))
        st.info(
            "Set `GSHEET_CREDS_JSON`/`credentials.json`, or set `BUFF_READ_SQLITE=1` with `BUFF_SQLITE_PATH`."
        )
        st.code(f"Fallback failed: {fallback_error}")
        st.stop()
        raise SystemExit(0)

if history_df.empty:
    history_df = fallback_history_frame()

history_before_fallback = len(history_df)
history_df = merge_fallback_history(history_df)
debug_log(f"ui after_fallback before={history_before_fallback} after={len(history_df)}")

required_cols = {"Timestamp", "Price", "Listings", "Family", "Skin Name", "Condition"}
if not required_cols.issubset(set(history_df.columns)):
    st.error("History data is missing required columns. Run `python main.py --migrate-only` once.")
    st.code(f"Missing columns: {sorted(required_cols - set(history_df.columns))}")
    st.stop()
    raise SystemExit(0)

history_before_prepare = len(history_df)
history_df = prepare_history_frame(history_df)
debug_log(f"ui after_prepare before={history_before_prepare} after={len(history_df)}")
history_before_value_filter = len(history_df)
history_df = filter_high_value_families(history_df, TRACK_KEYWORDS, HIGH_VALUE_MIN_PRICE)
debug_log(
    "ui after_value_filter "
    f"before={history_before_value_filter} after={len(history_df)} min_price={HIGH_VALUE_MIN_PRICE}"
)

if history_df.empty:
    st.warning(
        f"No knife families above {HIGH_VALUE_MIN_PRICE:,.0f} CNY yet. Run `python main.py` to refresh."
    )
    st.stop()
    raise SystemExit(0)

family_names = sorted(history_df["Family"].dropna().unique().tolist())

history_df["_Base Knife"] = history_df.get(
    "Knife Type", history_df["Family"].str.split("|").str[0]
).map(base_knife_type)
knife_counts = history_df.groupby("_Base Knife")["Family"].nunique().sort_index()
knife_types = [knife for knife in DEFAULT_TRACK_KEYWORDS if knife in knife_counts.index]

with st.sidebar:
    st.markdown(
        """
        <div class="buff-sidebar-head">
          <strong>BUFF163 Analytics</strong>
          <span>Market filters and refresh controls</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    selected_knife_type = st.selectbox(
        "Knife",
        knife_types,
        index=0,
        format_func=lambda value: f"{value} ({int(knife_counts.get(value, 0))})",
    )
    scoped_names = sorted(
        history_df.loc[history_df["_Base Knife"] == selected_knife_type, "Family"]
        .dropna()
        .unique()
        .tolist()
    )
    filtered_families = scoped_names or family_names
    latest_family = (
        history_df[history_df["Family"].isin(filtered_families)]
        .sort_values("Timestamp")
        .groupby("Family", as_index=False)
        .tail(1)[["Family", "Price", "Listings"]]
    )
    sort_option = st.selectbox(
        "Sort",
        ("Name A-Z", "Latest price high-low", "Latest price low-high", "Listings high-low"),
    )
    if sort_option == "Latest price high-low":
        filtered_families = latest_family.sort_values("Price", ascending=False)["Family"].tolist()
    elif sort_option == "Latest price low-high":
        filtered_families = latest_family.sort_values("Price", ascending=True)["Family"].tolist()
    elif sort_option == "Listings high-low":
        filtered_families = latest_family.sort_values("Listings", ascending=False)["Family"].tolist()

    family_selected = st.selectbox("Skin family", filtered_families, placeholder=f"{selected_knife_type} skins")

family_df = history_df[history_df["Family"] == family_selected].copy()

condition_latest = (
    family_df.sort_values("Timestamp")
    .assign(
        _source_key=lambda frame: frame.get("Source", pd.Series("", index=frame.index))
        .eq("Fallback")
        .astype(int)
    )
    .sort_values(["_source_key", "Timestamp"])
    .groupby("Condition", as_index=False)
    .tail(1)
    .assign(
        _sort_key=lambda frame: frame["Condition"].map(
            lambda value: CONDITION_ORDER.get(str(value), 50)
        )
    )
    .sort_values(["_sort_key", "Condition"])
)
condition_labels = [
    f"{row['Condition'] or 'Unknown'}  {float(row['Price']):,.2f} CNY"
    for _, row in condition_latest.iterrows()
]
condition_map = dict(zip(condition_labels, condition_latest["Condition"].tolist()))

with st.sidebar:
    selected_condition_label = st.selectbox("Condition", condition_labels)
    min_day = family_df["Timestamp"].min().date()
    max_day = family_df["Timestamp"].max().date()
    date_range = st.date_input("Date range", (min_day, max_day), min_value=min_day, max_value=max_day)
    if st.button("Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

condition_selected = condition_map[selected_condition_label]

variant_df = (
    family_df[family_df["Condition"] == condition_selected]
    .copy()
    .assign(
        _source_key=lambda frame: frame.get("Source", pd.Series("", index=frame.index))
        .eq("Fallback")
        .astype(int)
    )
    .sort_values(["_source_key", "Timestamp"])
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_day, end_day = date_range
else:
    start_day = end_day = date_range
range_mask = (variant_df["Timestamp"].dt.date >= start_day) & (variant_df["Timestamp"].dt.date <= end_day)
analysis_df = variant_df[range_mask].copy()
if analysis_df.empty:
    empty_state("No rows in the selected date range", "Showing the full available history for this condition instead.")
    analysis_df = variant_df.copy()
debug_log(
    "ui selection "
    f"family={family_selected!r} condition={condition_selected!r} "
    f"family_rows={len(family_df)} variant_rows={len(variant_df)} displayed_rows={len(analysis_df)} "
    f"date_start={start_day} date_end={end_day}"
)
if env_flag("BUFF_DEBUG_LISTINGS", False):
    with st.sidebar.expander("Debug counts"):
        st.caption(f"History rows: {len(history_df):,}")
        st.caption(f"Family rows: {len(family_df):,}")
        st.caption(f"Condition rows: {len(variant_df):,}")
        st.caption(f"Displayed rows: {len(analysis_df):,}")

latest = variant_df.iloc[-1]
image_url = choose_image_url(variant_df)
reference_price = (
    float(cast(Any, latest["Reference Price"]))
    if pd.notna(latest["Reference Price"])
    else float(cast(Any, latest["Price"]))
)
buy_orders = int(cast(Any, latest["Buy Orders"])) if pd.notna(latest["Buy Orders"]) else 0
sell_stock = int(cast(Any, latest["Listings"])) if pd.notna(latest["Listings"]) else 0
knife_category = family_selected.split("|")[0].strip()
goods_id = str(latest.get("Goods ID") or "N/A")
live_listing: dict[str, object] = {}
if os.getenv("BUFF_APP_LIVE_LISTINGS", "1").strip().lower() in {"1", "true", "yes", "on"}:
    live_listing = live_buff_listing(family_selected, condition_selected, knife_category)
    if live_listing.get("status") == "live":
        sell_stock = int(cast(Any, live_listing.get("listings") or 0))
        buy_orders = int(cast(Any, live_listing.get("buy_orders") or 0))
        goods_id = str(live_listing.get("goods_id") or goods_id)
        if live_listing.get("reference_price") is not None:
            reference_price = float(cast(Any, live_listing["reference_price"]))
        image_url = str(live_listing.get("image_url") or image_url)
listing_source = "BUFF" if sell_stock > 0 else "BUFF unavailable"
live_status = str(live_listing.get("status") or ("disabled" if not os.getenv("BUFF_APP_LIVE_LISTINGS", "1").strip().lower() in {"1", "true", "yes", "on"} else "not checked"))
live_checked = str(live_listing.get("checked_at") or "N/A")
status_class = "" if live_status == "live" else " buff-status-warn"
last_update = latest["Timestamp"].strftime("%Y-%m-%d %H:%M UTC")

st.markdown(
    f"""
    <div class="buff-header">
      <div>
        <h1>BUFF163 Price Analytics</h1>
        <p>{family_selected} | {condition_selected} | {knife_category} | Goods ID {goods_id}</p>
        <p>Last update: {last_update} | Checked: {live_checked} | Auto refresh: {max(30, REFRESH_SECONDS) // 60} min</p>
      </div>
      <div class="buff-status{status_class}">Market {live_status}</div>
    </div>
    <div class="buff-hero">
      <div class="buff-grid">
        <div class="buff-image-card">
          {f'<img class="buff-knife-art" src="{image_url}" alt="{family_selected}">' if image_url else '<div style="color:#aab6ca;">No image available</div>'}
        </div>
        <div>
          <h1 class="buff-title">{family_selected}</h1>
          <div class="buff-submeta">
            <span>Condition | {condition_selected}</span>
            <span>Listings | {sell_stock if sell_stock else 'N/A'} ({listing_source})</span>
            <span>Buy orders | {buy_orders}</span>
          </div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

render_kpis(analysis_df, sell_stock, buy_orders, reference_price)

daily_df = analysis_df.copy()
if "Listings" in daily_df.columns:
    daily_df.loc[daily_df["Listings"].fillna(0) <= 0, "Listings"] = pd.NA
daily_df["Day"] = daily_df["Timestamp"].dt.date
daily_df = daily_df.groupby("Day", as_index=False).agg(
    Price=("Price", "mean"),
    Listings=("Listings", "last"),
    BuyOrders=("Buy Orders", "last"),
)
daily_df["Day"] = pd.to_datetime(daily_df["Day"])
daily_df["Moving Average"] = daily_df["Price"].rolling(7, min_periods=1).mean()
high_point = daily_df[daily_df["Price"] == daily_df["Price"].max()]
low_point = daily_df[daily_df["Price"] == daily_df["Price"].min()]
chart_tooltip = [
    alt.Tooltip("Day:T", title="Date"),
    alt.Tooltip("Price:Q", title="Avg Price", format=",.2f"),
    alt.Tooltip("Moving Average:Q", title="7D MA", format=",.2f"),
    alt.Tooltip("Listings:Q", title="Listings", format=",.0f"),
    alt.Tooltip("BuyOrders:Q", title="Buy Orders", format=",.0f"),
]

price_chart = (
    alt.Chart(daily_df)
    .mark_line(color="#f0a23b", interpolate="monotone", strokeWidth=3)
    .encode(
        x=alt.X("Day:T", title="Date", axis=alt.Axis(labelColor="#9eabc0", titleColor="#c6cfdd")),
        y=alt.Y("Price:Q", title="Price (CNY)", axis=alt.Axis(labelColor="#9eabc0", titleColor="#c6cfdd")),
        tooltip=chart_tooltip,
    )
    .properties(height=320)
)
moving_average = (
    alt.Chart(daily_df)
    .mark_line(color="#49a078", interpolate="monotone", strokeDash=[6, 4], strokeWidth=2)
    .encode(x="Day:T", y=alt.Y("Moving Average:Q", axis=None), tooltip=chart_tooltip)
)
extreme_points = alt.layer(
    alt.Chart(high_point).mark_point(color="#ff6b6b", filled=True, size=90).encode(x="Day:T", y=alt.Y("Price:Q", axis=None), tooltip=chart_tooltip),
    alt.Chart(low_point).mark_point(color="#6dd6ff", filled=True, size=90).encode(x="Day:T", y=alt.Y("Price:Q", axis=None), tooltip=chart_tooltip),
)
stock_chart = (
    alt.Chart(daily_df)
    .mark_area(color="#5f7bd0", opacity=0.28, interpolate="monotone")
    .encode(
        x=alt.X("Day:T", title="Date", axis=alt.Axis(labelColor="#9eabc0", titleColor="#c6cfdd")),
        y=alt.Y("Listings:Q", title="Sell Stock", axis=alt.Axis(labelColor="#9eabc0", titleColor="#c6cfdd")),
        tooltip=chart_tooltip,
    )
    .properties(height=180)
)

stock_overlay = (
    alt.Chart(daily_df)
    .mark_line(color="#5f7bd0", interpolate="monotone", strokeWidth=2.2, opacity=0.85)
    .encode(
        x=alt.X("Day:T", title="Date"),
        y=alt.Y(
            "Listings:Q",
            title="Sell Stock",
            axis=alt.Axis(orient="right", labelColor="#aab6ca", titleColor="#aab6ca"),
        ),
        tooltip=chart_tooltip,
    )
    .properties(height=320)
)
price_layers = alt.layer(price_chart, moving_average, extreme_points)
combined_chart = alt.layer(price_chart, moving_average, extreme_points, stock_overlay).resolve_scale(y="independent")

left, right = st.columns((2.2, 1))

with left:
    section_title("Price Trend", "Daily average, 7-day moving average, and day-end stock")
    chart_mode = st.radio(
        "Chart mode",
        ("Combined (Price + Stock)", "Stacked (Price above Stock)"),
        horizontal=True,
        label_visibility="collapsed",
    )
    if chart_mode.startswith("Combined"):
        st.altair_chart(combined_chart, width="stretch")
    else:
        st.altair_chart((price_layers & stock_chart).resolve_scale(x="shared"), width="stretch")

with right:
    summary = (
        analysis_df[["Timestamp", "Price", "Listings", "Buy Orders"]]
        .sort_values("Timestamp", ascending=False)
        .head(8)
        .copy()
    )
    summary["Listings"] = summary["Listings"].fillna(0).astype(int)
    summary["Buy Orders"] = summary["Buy Orders"].fillna(0).astype(int)
    summary["Timestamp"] = summary["Timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    section_title("Recent Selling Points", "Sell / buy depth")
    st.dataframe(format_market_table(summary), width="stretch", hide_index=True)

tab1, tab2, tab3, tab4 = st.tabs(["Sell History", "Condition Catalog", "Forecast", "Full Catalog"])

with tab1:
    section_title("Sell History", "Filtered historical observations")
    sell_view = analysis_df[
        ["Timestamp", "Price", "Listings", "Buy Orders", "Reference Price", "Observed Orders"]
    ].sort_values("Timestamp", ascending=False)
    if sell_view.empty:
        empty_state("No sell history", "Try widening the date range in the sidebar.")
    else:
        sell_view["Listings"] = sell_view["Listings"].fillna(0).astype(int)
        sell_view["Buy Orders"] = sell_view["Buy Orders"].fillna(0).astype(int)
        sell_view["Observed Orders"] = (
            pd.to_numeric(sell_view["Observed Orders"], errors="coerce")
            .fillna(0)
            .astype(int)
        )
        st.dataframe(format_market_table(sell_view), width="stretch", hide_index=True)

with tab2:
    section_title("Condition Catalog", "Latest catalog rows for this family")
    if catalog_df.empty:
        with st.spinner("Loading condition catalog..."):
            catalog_df = load_sheet_records(CATALOG_SHEET_NAME)
    if catalog_df.empty:
        empty_state("Catalog sheet is empty", "Run the catalog sync to populate condition rows.")
    else:
        catalog_df["Price"] = pd.to_numeric(catalog_df["Price"], errors="coerce")
        catalog_df["Listings"] = pd.to_numeric(catalog_df["Listings"], errors="coerce")
        catalog_df["Buy Orders"] = pd.to_numeric(catalog_df["Buy Orders"], errors="coerce")
        catalog_df["Condition"] = catalog_df["Condition"].fillna("Unknown").astype(str)
        family_catalog = (
            catalog_df[catalog_df["Family"] == family_selected]
            .assign(
                _sort_key=lambda frame: frame["Condition"].map(
                    lambda value: CONDITION_ORDER.get(str(value), 50)
                )
            )
            .sort_values(["_sort_key", "Condition"])
            .drop(columns=["_sort_key"])
        )
        family_catalog["Listings"] = family_catalog["Listings"].fillna(0).astype(int)
        family_catalog["Buy Orders"] = family_catalog["Buy Orders"].fillna(0).astype(int)
        table = family_catalog[
            ["Skin Name", "Condition", "Price", "Listings", "Buy Orders", "Goods ID"]
        ]
        if table.empty:
            empty_state(
                "No catalog rows for this family",
                "Select another family or refresh the catalog source.",
            )
        else:
            st.dataframe(format_market_table(table), width="stretch", hide_index=True)

with tab3:
    section_title("Forecast", "Projected price and listing depth")
    if forecast_df.empty:
        with st.spinner("Loading forecast..."):
            forecast_df = load_sheet_records(FORECAST_SHEET_NAME)
    if forecast_df.empty:
        empty_state("Forecast sheet is empty", "Forecast rows will appear here after the forecast job runs.")
    else:
        forecast_df["Forecast Date"] = pd.to_datetime(forecast_df["Forecast Date"], errors="coerce")
        forecast_df["Predicted Price"] = pd.to_numeric(
            forecast_df.get("Predicted Price"), errors="coerce"
        )
        if "Predicted Listings" in forecast_df.columns:
            forecast_df["Predicted Listings"] = pd.to_numeric(
                forecast_df.get("Predicted Listings"), errors="coerce"
            )
        target_skin_name = f"{family_selected} ({condition_selected})"
        forecast_view = forecast_df[forecast_df["Skin Name"] == target_skin_name].dropna()
        if forecast_view.empty:
            empty_state("No forecast rows for this condition", "Choose another condition or refresh after forecasting completes.")
        else:
            if "Predicted Listings" in forecast_view.columns:
                price_forecast = (
                    alt.Chart(forecast_view)
                    .mark_line(point=True, color="#49a078", interpolate="monotone", strokeWidth=3)
                    .encode(
                        x=alt.X("Forecast Date:T", title="Date"),
                        y=alt.Y("Predicted Price:Q", title="Predicted Price (CNY)"),
                        tooltip=[
                            "Forecast Date:T",
                            "Predicted Price:Q",
                            "Predicted Listings:Q",
                            "Model:N",
                        ],
                    )
                    .properties(height=320)
                )
                listings_forecast = (
                    alt.Chart(forecast_view)
                    .mark_line(color="#5f7bd0", point=True, interpolate="monotone", strokeWidth=2.5, opacity=0.85)
                    .encode(
                        x=alt.X("Forecast Date:T", title="Date"),
                        y=alt.Y(
                            "Predicted Listings:Q",
                            title="Predicted Sell Stock",
                            axis=alt.Axis(orient="right"),
                        ),
                        tooltip=[
                            "Forecast Date:T",
                            "Predicted Price:Q",
                            "Predicted Listings:Q",
                            "Model:N",
                        ],
                    )
                    .properties(height=320)
                )
                st.altair_chart(
                    alt.layer(price_forecast, listings_forecast).resolve_scale(y="independent"),
                    width="stretch",
                )
                show_cols = [
                    col
                    for col in ("Forecast Date", "Predicted Price", "Predicted Listings", "Model")
                    if col in forecast_view.columns
                ]
                st.dataframe(
                    format_market_table(forecast_view[show_cols].sort_values("Forecast Date")),
                    width="stretch",
                    hide_index=True,
                )
            else:
                forecast_chart = (
                    alt.Chart(forecast_view)
                    .mark_line(point=True, color="#49a078", interpolate="monotone", strokeWidth=3)
                    .encode(
                        x=alt.X("Forecast Date:T", title="Date"),
                        y=alt.Y("Predicted Price:Q", title="Predicted Price (CNY)"),
                        tooltip=["Forecast Date:T", "Predicted Price:Q"],
                    )
                    .properties(height=320)
                )
                st.altair_chart(forecast_chart, width="stretch")

with tab4:
    section_title("Full Catalog", "On-demand catalog table")
    if "load_full_catalog" not in st.session_state:
        st.session_state["load_full_catalog"] = False
    col_load, col_hint = st.columns((1, 3))
    with col_load:
        if st.button("Load Full Catalog"):
            st.session_state["load_full_catalog"] = True
    with col_hint:
        st.caption("This sheet can be large; loading on demand keeps the app fast.")

    if st.session_state["load_full_catalog"] and all_catalog_df.empty:
        with st.spinner("Loading full catalog..."):
            all_catalog_df = load_sheet_records(ALL_CATALOG_SHEET_NAME)

    if all_catalog_df.empty:
        empty_state("Full catalog not loaded", "Click Load Full Catalog to fetch the larger sheet on demand.")
    else:
        for numeric_col in ("Price", "Listings", "Buy Orders", "Reference Price"):
            if numeric_col in all_catalog_df.columns:
                all_catalog_df[numeric_col] = pd.to_numeric(
                    all_catalog_df[numeric_col], errors="coerce"
                )
        all_catalog_df["Family"] = all_catalog_df.get("Family", "").fillna("").astype(str)
        scoped = (
            all_catalog_df[all_catalog_df["Family"] == family_selected].copy()
            if family_selected
            else all_catalog_df.copy()
        )
        catalog_cols = [
            c
            for c in (
                "Timestamp",
                "Skin Name",
                "Condition",
                "Price",
                "Listings",
                "Buy Orders",
                "Reference Price",
                "Goods ID",
                "Goods URL",
                "Image URL",
            )
            if c in scoped.columns
        ]
        table = scoped[catalog_cols].sort_values(
            ["Price"], ascending=False, na_position="last"
        )
        if table.empty:
            empty_state(
                "No full catalog rows for this family",
                "Select another family or reload the source data.",
            )
        else:
            st.dataframe(format_market_table(table), width="stretch", hide_index=True)
