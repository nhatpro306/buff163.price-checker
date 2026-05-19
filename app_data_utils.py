from __future__ import annotations

from collections.abc import Callable

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
            # SQLite mode is for local testing without Google Sheets credentials.
            history_df = load_sqlite_history(sqlite_path)
            return history_df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None

        history_df = load_sheet_history()
        # Heavy sheets are loaded lazily in UI tabs to keep startup responsive.
        catalog_df = pd.DataFrame()
        all_catalog_df = pd.DataFrame()
        forecast_df = pd.DataFrame()
        return history_df, catalog_df, all_catalog_df, forecast_df, None
    except Exception as exc:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), exc


def prepare_history_frame(history_df: pd.DataFrame) -> pd.DataFrame:
    frame = history_df.copy()
    # Normalize spreadsheet values before filtering/charting. Google Sheets can
    # return numbers as strings, especially after manual edits.
    frame["Timestamp"] = pd.to_datetime(frame["Timestamp"], errors="coerce", utc=True)
    frame["Price"] = pd.to_numeric(frame["Price"], errors="coerce")
    frame["Listings"] = pd.to_numeric(frame["Listings"], errors="coerce")
    frame["Buy Orders"] = pd.to_numeric(frame.get("Buy Orders"), errors="coerce")
    frame["Reference Price"] = pd.to_numeric(frame.get("Reference Price"), errors="coerce")
    frame["Family"] = frame["Family"].fillna("").astype(str)
    frame["Skin Name"] = frame["Skin Name"].fillna("").astype(str)
    frame["Condition"] = frame["Condition"].fillna("Unknown").astype(str)
    frame["Image URL"] = frame.get("Image URL", "").fillna("").astype(str)
    frame = frame.dropna(subset=["Timestamp", "Family", "Skin Name", "Price"]).sort_values(
        "Timestamp"
    )
    return frame


def filter_high_value_families(
    history_df: pd.DataFrame, keywords: tuple[str, ...], min_price: float
) -> pd.DataFrame:
    frame = history_df.copy()
    family_mask = frame["Family"].str.contains("|".join(keywords), case=False, na=False)
    frame = frame[family_mask].copy()
    latest_family_prices = (
        frame.sort_values("Timestamp")
        .groupby("Family", as_index=False)
        .tail(1)[["Family", "Price"]]
    )
    high_value_families = latest_family_prices[latest_family_prices["Price"] >= min_price][
        "Family"
    ].tolist()
    return frame[frame["Family"].isin(high_value_families)].copy()


def choose_image_url(variant_df: pd.DataFrame) -> str:
    for frame in (variant_df,):
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


def filter_fallback_overrides_same_day(
    history: pd.DataFrame, fallback: pd.DataFrame
) -> pd.DataFrame:
    """Drop fallback rows when direct history already has same-day data.

    This prevents fallback listing values from overriding fresh BUFF listings
    for the same Family+Condition on the same date.
    """
    if history.empty or fallback.empty:
        return fallback.copy()

    required_cols = {"Timestamp", "Family", "Condition"}
    if not required_cols.issubset(history.columns) or not required_cols.issubset(fallback.columns):
        return fallback.copy()

    hist = history.copy()
    fb = fallback.copy()
    hist["Timestamp"] = pd.to_datetime(hist["Timestamp"], errors="coerce", utc=True)
    fb["Timestamp"] = pd.to_datetime(fb["Timestamp"], errors="coerce", utc=True)
    hist = hist.dropna(subset=["Timestamp"])
    fb = fb.dropna(subset=["Timestamp"])
    if hist.empty or fb.empty:
        return fb

    hist["__day"] = hist["Timestamp"].dt.strftime("%Y-%m-%d")
    fb["__day"] = fb["Timestamp"].dt.strftime("%Y-%m-%d")

    existing = set(
        zip(hist["Family"].astype(str), hist["Condition"].astype(str), hist["__day"].astype(str))
    )
    mask = [
        (str(fam), str(cond), str(day)) not in existing
        for fam, cond, day in zip(fb["Family"], fb["Condition"], fb["__day"])
    ]
    return fb.loc[mask].drop(columns=["__day"])


def filter_depthless_fallback_rows(fallback: pd.DataFrame) -> pd.DataFrame:
    if fallback.empty:
        return fallback.copy()
    frame = fallback.copy()
    listings = pd.to_numeric(frame.get("Listings"), errors="coerce").fillna(0)
    buy_orders = pd.to_numeric(frame.get("Buy Orders"), errors="coerce").fillna(0)
    return frame[(listings > 0) | (buy_orders > 0)].copy()
