from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd


def load_app_frames(
    *,
    use_sqlite: bool,
    sqlite_path: str,
    load_sqlite_history: Callable[[str], pd.DataFrame],
    load_sheet_history: Callable[[], pd.DataFrame],
    load_sheet_records: Callable[[str], pd.DataFrame],
    catalog_sheet_name: str,
    all_catalog_sheet_name: str,
    forecast_sheet_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Exception | None]:
    try:
        if use_sqlite and sqlite_path:
            history_df = load_sqlite_history(sqlite_path)
            return history_df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None

        history_df = load_sheet_history()
        catalog_df = load_sheet_records(catalog_sheet_name)
        # Heavy sheets are loaded lazily in UI tabs to keep startup responsive.
        all_catalog_df = pd.DataFrame()
        forecast_df = pd.DataFrame()
        return history_df, catalog_df, all_catalog_df, forecast_df, None
    except Exception as exc:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), exc


def prepare_history_frame(history_df: pd.DataFrame) -> pd.DataFrame:
    frame = history_df.copy()
    frame["Timestamp"] = pd.to_datetime(frame["Timestamp"], errors="coerce", utc=True)
    frame["Price"] = pd.to_numeric(frame["Price"], errors="coerce")
    frame["Listings"] = pd.to_numeric(frame["Listings"], errors="coerce")
    frame["Buy Orders"] = pd.to_numeric(frame.get("Buy Orders"), errors="coerce")
    frame["Reference Price"] = pd.to_numeric(frame.get("Reference Price"), errors="coerce")
    frame["Family"] = frame["Family"].fillna("").astype(str)
    frame["Skin Name"] = frame["Skin Name"].fillna("").astype(str)
    frame["Condition"] = frame["Condition"].fillna("Unknown").astype(str)
    frame["Image URL"] = frame.get("Image URL", "").fillna("").astype(str)
    frame = frame.dropna(subset=["Timestamp", "Family", "Skin Name", "Price"]).sort_values("Timestamp")
    return frame


def filter_high_value_families(history_df: pd.DataFrame, keywords: tuple[str, ...], min_price: float) -> pd.DataFrame:
    frame = history_df.copy()
    family_mask = frame["Family"].str.contains("|".join(keywords), case=False, na=False)
    frame = frame[family_mask].copy()
    latest_family_prices = (
        frame.sort_values("Timestamp")
        .groupby("Family", as_index=False)
        .tail(1)[["Family", "Price"]]
    )
    high_value_families = latest_family_prices[latest_family_prices["Price"] >= min_price]["Family"].tolist()
    return frame[frame["Family"].isin(high_value_families)].copy()


def choose_image_url(variant_df: pd.DataFrame, family_df: pd.DataFrame, history_df: pd.DataFrame) -> str:
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
