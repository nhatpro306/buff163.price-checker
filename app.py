from __future__ import annotations

import html
import os
from typing import Any, cast

import pandas as pd
import streamlit as st

from src.dashboard.runtime import (
    HIGH_VALUE_MIN_PRICE,
    REFRESH_SECONDS,
    TRACK_KEYWORDS,
    configure_page,
)
from src.dashboard.data_sources import (
    fallback_history_frame,
    live_buff_listing,
    load_history_records,
    load_sheet_records,
    merge_fallback_history,
)
from src.dashboard.frames import (
    choose_image_url,
    filter_high_value_families,
    load_app_frames,
    prepare_history_frame,
)
from src.dashboard.kpis import money, whole
from src.dashboard.sections import (
    render_forecast,
    render_hero,
    render_kpis,
    render_price_history_and_activity,
    render_recent_listings,
    render_top_movers,
)
from src.dashboard.formatting import (
    base_knife_type,
    empty_state,
)
from src.dashboard.filters import render_sidebar
from src.dashboard.theme import inject_styles
from main import (
    ALL_CATALOG_SHEET_NAME,
    CATALOG_SHEET_NAME,
    FORECAST_SHEET_NAME,
    sqlite_load_history_frame,
)
from market_utils import debug_log, env_flag

configure_page()
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
selection = render_sidebar(history_df, family_names)
selected_knife_type = selection.selected_knife_type
family_selected = selection.family_selected
condition_selected = selection.condition_selected
date_range = selection.date_range
family_df = selection.family_df

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
range_mask = (variant_df["Timestamp"].dt.date >= start_day) & (
    variant_df["Timestamp"].dt.date <= end_day
)
analysis_df = variant_df[range_mask].copy()
if analysis_df.empty:
    empty_state(
        "No rows in the selected date range",
        "Showing the full available history for this condition instead.",
    )
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
if os.getenv("BUFF_APP_LIVE_LISTINGS", "0").strip().lower() in {"1", "true", "yes", "on"}:
    live_listing = live_buff_listing(family_selected, condition_selected, knife_category)
    if live_listing.get("status") == "live":
        sell_stock = int(cast(Any, live_listing.get("listings") or 0))
        buy_orders = int(cast(Any, live_listing.get("buy_orders") or 0))
        goods_id = str(live_listing.get("goods_id") or goods_id)
        if live_listing.get("reference_price") is not None:
            reference_price = float(cast(Any, live_listing["reference_price"]))
        image_url = str(live_listing.get("image_url") or image_url)
listing_source = "BUFF" if sell_stock > 0 else "BUFF unavailable"
live_status = str(
    live_listing.get("status")
    or (
        "disabled"
        if os.getenv("BUFF_APP_LIVE_LISTINGS", "0").strip().lower()
        not in {"1", "true", "yes", "on"}
        else "not checked"
    )
)
live_checked = str(live_listing.get("checked_at") or "N/A")
status_class = "" if live_status == "live" else " buff-status-warn"
last_update = latest["Timestamp"].strftime("%Y-%m-%d %H:%M UTC")
latest_price_label = money(latest["Price"])
price_series = pd.to_numeric(analysis_df["Price"], errors="coerce").dropna()
average_price_label = money(price_series.mean() if not price_series.empty else pd.NA)
highest_price_label = money(price_series.max() if not price_series.empty else pd.NA)
lowest_price_label = money(price_series.min() if not price_series.empty else pd.NA)
reference_price_label = money(reference_price)
sell_stock_label = whole(sell_stock)
buy_orders_label = whole(buy_orders)
condition_label = html.escape(condition_selected)
family_label = html.escape(family_selected)
knife_label = html.escape(knife_category)
goods_id_label = html.escape(goods_id)
live_status_label = html.escape(live_status)
last_update_label = html.escape(last_update)
live_checked_label = html.escape(live_checked)
image_html = (
    f'<img class="buff-knife-art" src="{html.escape(image_url)}" alt="{family_label}">'
    if image_url
    else '<div style="color:#aab6ca;">No image available</div>'
)

render_hero(
    family_label=family_label,
    condition_label=condition_label,
    knife_label=knife_label,
    goods_id_label=goods_id_label,
    last_update_label=last_update_label,
    live_checked_label=live_checked_label,
    status_class=status_class,
    live_status_label=live_status_label,
    image_html=image_html,
    latest_price_label=latest_price_label,
    average_price_label=average_price_label,
    highest_price_label=highest_price_label,
    lowest_price_label=lowest_price_label,
    sell_stock_label=sell_stock_label,
    reference_price_label=reference_price_label,
    buy_orders_label=buy_orders_label,
    listing_source=html.escape(listing_source),
    refresh_minutes=max(30, REFRESH_SECONDS) // 60,
)
render_kpis(analysis_df, sell_stock)
render_price_history_and_activity(analysis_df, sell_stock, buy_orders)
render_forecast(
    forecast_df,
    family_selected=family_selected,
    condition_selected=condition_selected,
    load_sheet_records=load_sheet_records,
)
render_top_movers(history_df, selected_knife_type)
render_recent_listings(analysis_df)
