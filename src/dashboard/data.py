from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from gspread import WorksheetNotFound

from src.dashboard.config import CACHE_TTL_SECONDS, HIGH_VALUE_MIN_PRICE, TRACK_KEYWORDS
from src.dashboard.data_utils import (
    filter_depthless_fallback_rows,
    filter_fallback_overrides_same_day,
)
from src.dashboard.ui import base_knife_type
from main import (
    CATALOG_HEADERS,
    CATALOG_SHEET_NAME,
    DEFAULT_KNIFE_CATEGORIES,
    SHEET_NAME,
    BuffPriceClient,
    SheetStore,
    csgotrader_snapshots,
    load_history_frame,
)
from market_utils import debug_log


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
    if os.getenv("BUFF_APP_FALLBACK_CSGOTRADER", "0").strip().lower() not in {
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
        fallback = filter_depthless_fallback_rows(fallback)
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
    fallback = filter_depthless_fallback_rows(fallback)
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
