from __future__ import annotations

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
    frame = frame.dropna(subset=["Timestamp", "Family", "Skin Name", "Price"]).sort_values("Timestamp")
    return frame


def filter_high_value_families(history_df: pd.DataFrame, keywords: tuple[str, ...], min_price: float) -> pd.DataFrame:
    frame = history_df.copy()
    family_mask = frame["Family"].str.contains("|".join(keywords), case=False, na=False)
    frame = frame[family_mask].copy()
    latest_family_prices = frame.sort_values("Timestamp").groupby("Family", as_index=False).tail(1)[["Family", "Price"]]
    high_value_families = latest_family_prices[latest_family_prices["Price"] >= min_price]["Family"].tolist()
    return frame[frame["Family"].isin(high_value_families)].copy()


def choose_image_url(variant_df: pd.DataFrame) -> str:
    for frame in (variant_df,):
        candidates = frame.get("Image URL")
        if candidates is None:
            continue
        non_empty = candidates.astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA}).dropna()
        if not non_empty.empty:
            return str(non_empty.iloc[-1])
    return ""


def build_variant_daily_frame(variant_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate variant history to one row per day for charting."""
    daily_df = variant_df.copy()
    if "Listings" in daily_df.columns:
        daily_df.loc[daily_df["Listings"].fillna(0) <= 0, "Listings"] = pd.NA
    daily_df["Day"] = pd.to_datetime(daily_df["Timestamp"], errors="coerce", utc=True).dt.date
    daily_df = daily_df.groupby("Day", as_index=False).agg(
        Price=("Price", "mean"),
        Listings=("Listings", "last"),
        BuyOrders=("Buy Orders", "last"),
    )
    daily_df["Day"] = pd.to_datetime(daily_df["Day"], errors="coerce")
    return daily_df.dropna(subset=["Day"]).sort_values("Day")


def build_recent_points_table(variant_df: pd.DataFrame, limit: int = 8) -> pd.DataFrame:
    """Prepare compact recent rows for side panel table."""
    summary = (
        variant_df[["Timestamp", "Price", "Listings", "Buy Orders"]]
        .sort_values("Timestamp", ascending=False)
        .head(limit)
        .copy()
    )
    summary["Listings"] = pd.to_numeric(summary["Listings"], errors="coerce").fillna(0).astype(int)
    summary["Buy Orders"] = pd.to_numeric(summary["Buy Orders"], errors="coerce").fillna(0).astype(int)
    summary["Timestamp"] = pd.to_datetime(summary["Timestamp"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d %H:%M")
    return summary


def build_sell_history_table(variant_df: pd.DataFrame) -> pd.DataFrame:
    """Prepare full sell history rows for tabular display."""
    sell_view = variant_df[
        ["Timestamp", "Price", "Listings", "Buy Orders", "Reference Price", "Observed Orders"]
    ].sort_values("Timestamp", ascending=False)
    sell_view = sell_view.copy()
    sell_view["Listings"] = pd.to_numeric(sell_view["Listings"], errors="coerce").fillna(0).astype(int)
    sell_view["Buy Orders"] = pd.to_numeric(sell_view["Buy Orders"], errors="coerce").fillna(0).astype(int)
    sell_view["Observed Orders"] = pd.to_numeric(sell_view["Observed Orders"], errors="coerce").fillna(0).astype(int)
    return sell_view


def build_variant_metrics(variant_df: pd.DataFrame) -> dict[str, object]:
    """Compute display metrics from the current variant history."""
    if variant_df.empty:
        return {
            "latest_price": None,
            "reference_price": None,
            "buy_orders": 0,
            "sell_stock": 0,
            "last_update": None,
        }
    latest = variant_df.iloc[-1]
    latest_price = float(pd.to_numeric(latest.get("Price"), errors="coerce"))
    reference_value = pd.to_numeric(latest.get("Reference Price"), errors="coerce")
    reference_price = float(reference_value) if pd.notna(reference_value) else latest_price
    buy_orders = int(pd.to_numeric(latest.get("Buy Orders"), errors="coerce") or 0)
    sell_stock = int(pd.to_numeric(latest.get("Listings"), errors="coerce") or 0)
    last_update = pd.to_datetime(latest.get("Timestamp"), errors="coerce", utc=True)
    return {
        "latest_price": latest_price,
        "reference_price": reference_price,
        "buy_orders": buy_orders,
        "sell_stock": sell_stock,
        "last_update": last_update,
    }


def filter_fallback_overrides_same_day(history: pd.DataFrame, fallback: pd.DataFrame) -> pd.DataFrame:
    """Keep fallback rows only when history has no same-day row for that key.

    Prevents fallback data from overriding fresh direct BUFF listing rows in the
    dashboard when both sources contain the same Family+Condition on the same
    date.
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
        zip(
            hist["Family"].astype(str),
            hist["Condition"].astype(str),
            hist["__day"].astype(str),
        )
    )
    mask = [
        (str(fam), str(cond), str(day)) not in existing
        for fam, cond, day in zip(fb["Family"], fb["Condition"], fb["__day"])
    ]
    return fb.loc[mask].drop(columns=["__day"])


def pick_first_existing_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    for name in candidates:
        if name in frame.columns:
            return name
    return None


def infer_dashboard_columns(frame: pd.DataFrame) -> dict[str, str | None]:
    return {
        "price": pick_first_existing_column(frame, ["Price", "Latest Price", "Predicted Price"]),
        "timestamp": pick_first_existing_column(frame, ["Timestamp", "Date", "Datetime", "Updated At"]),
        "skin": pick_first_existing_column(frame, ["Skin Name", "Family", "Item", "Name"]),
        "condition": pick_first_existing_column(frame, ["Condition"]),
        "listings": pick_first_existing_column(frame, ["Listings", "Sell Listings"]),
        "buy_orders": pick_first_existing_column(frame, ["Buy Orders", "BuyOrders"]),
    }


def apply_analytics_filters(
    frame: pd.DataFrame,
    *,
    skin_col: str | None,
    condition_col: str | None,
    timestamp_col: str | None,
    skin_value: str | None,
    condition_value: str | None,
    date_start: pd.Timestamp | None,
    date_end: pd.Timestamp | None,
) -> pd.DataFrame:
    filtered = frame.copy()
    if skin_col and skin_value and skin_value != "All":
        filtered = filtered[filtered[skin_col].astype(str) == skin_value]
    if condition_col and condition_value and condition_value != "All":
        filtered = filtered[filtered[condition_col].astype(str) == condition_value]
    if timestamp_col and timestamp_col in filtered.columns and (date_start is not None or date_end is not None):
        ts = pd.to_datetime(filtered[timestamp_col], errors="coerce", utc=True)
        if date_start is not None:
            filtered = filtered[ts >= pd.Timestamp(date_start).tz_localize("UTC")]
        if date_end is not None:
            filtered = filtered[ts <= (pd.Timestamp(date_end).tz_localize("UTC") + pd.Timedelta(days=1))]
    return filtered


def build_overview_metrics(frame: pd.DataFrame, *, price_col: str, timestamp_col: str | None) -> dict[str, object]:
    prices = pd.to_numeric(frame[price_col], errors="coerce").dropna()
    if prices.empty:
        return {
            "latest": None,
            "average": None,
            "highest": None,
            "lowest": None,
            "change_pct": None,
            "latest_update": None,
        }
    latest_price = float(prices.iloc[-1])
    first_price = float(prices.iloc[0])
    change_pct = ((latest_price - first_price) / first_price * 100.0) if first_price else None
    latest_update = None
    if timestamp_col and timestamp_col in frame.columns:
        latest_update = pd.to_datetime(frame[timestamp_col], errors="coerce", utc=True).max()
    return {
        "latest": latest_price,
        "average": float(prices.mean()),
        "highest": float(prices.max()),
        "lowest": float(prices.min()),
        "change_pct": float(change_pct) if change_pct is not None else None,
        "latest_update": latest_update,
    }


def build_price_history_frame(frame: pd.DataFrame, *, price_col: str, timestamp_col: str) -> pd.DataFrame:
    history = frame.copy()
    history["__ts"] = pd.to_datetime(history[timestamp_col], errors="coerce", utc=True)
    history["__price"] = pd.to_numeric(history[price_col], errors="coerce")
    history = history.dropna(subset=["__ts", "__price"]).sort_values("__ts")
    if history.empty:
        return pd.DataFrame(columns=["Date", "Price"])
    daily = history.assign(Date=history["__ts"].dt.date).groupby("Date", as_index=False).agg(Price=("__price", "mean"))
    daily["Date"] = pd.to_datetime(daily["Date"], errors="coerce")
    return daily


def build_listing_data_table(
    frame: pd.DataFrame,
    *,
    timestamp_col: str | None,
    price_col: str | None,
    listings_col: str | None,
    buy_orders_col: str | None,
) -> pd.DataFrame:
    cols: list[str] = []
    for col in (timestamp_col, price_col, listings_col, buy_orders_col):
        if col and col in frame.columns and col not in cols:
            cols.append(col)
    if not cols:
        return pd.DataFrame()
    table = frame[cols].copy()
    if timestamp_col and timestamp_col in table.columns:
        table[timestamp_col] = pd.to_datetime(table[timestamp_col], errors="coerce", utc=True)
        table = table.sort_values(timestamp_col, ascending=False, na_position="last")
    if listings_col and listings_col in table.columns:
        table[listings_col] = pd.to_numeric(table[listings_col], errors="coerce").fillna(0).astype(int)
    if buy_orders_col and buy_orders_col in table.columns:
        table[buy_orders_col] = pd.to_numeric(table[buy_orders_col], errors="coerce").fillna(0).astype(int)
    if price_col and price_col in table.columns:
        table[price_col] = pd.to_numeric(table[price_col], errors="coerce")
    return table
