from __future__ import annotations

import os
from typing import Any

import gspread
import pandas as pd
import requests

from market_config import (
    ALL_CATALOG_HEADERS,
    ALL_CATALOG_SHEET_NAME,
    CATALOG_HEADERS,
    CATALOG_SHEET_NAME,
    CONDITION_ORDER,
    CSGOTRADER_BUFF_URL,
    DASHBOARD_SHEET_NAME,
    DEFAULT_TRACK_KEYWORDS,
    FORECAST_SHEET_NAME,
    HISTORY_HEADERS,
    LOG_SHEET_NAME,
    SIGNALS_SHEET_NAME,
    STEAM_IMAGE_CACHE_PATH,
)
from market_models import MarketSnapshot
from market_utils import (
    csgo_api_image_map,
    env_flag,
    load_json_file,
    save_json_file,
    source_id,
    split_market_name,
    steam_image_url,
    try_float,
)
from src.etl import normalize_history_values
from src.storage.credentials import load_google_credentials

_GOODS_PAGE_URL = "https://buff.163.com/goods/{goods_id}?from=market#tab=selling"


class SheetStore:
    def __init__(self, sheet_name: str) -> None:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = load_google_credentials(scope)
        self.client = gspread.authorize(creds)
        if sheet_name.startswith("https://docs.google.com/spreadsheets/"):
            self.spreadsheet = self.client.open_by_url(sheet_name)
        else:
            try:
                self.spreadsheet = self.client.open(sheet_name)
            except gspread.SpreadsheetNotFound:
                self.spreadsheet = self.client.create(sheet_name)

    def worksheet(self, title: str, headers: list[str], rows: int = 2000, cols: int = 20):
        try:
            sheet = self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            sheet = self.spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)
            sheet.append_row(headers)
        return sheet

    def history_rows(self) -> list[dict[str, Any]]:
        sheet = self.worksheet(LOG_SHEET_NAME, HISTORY_HEADERS)
        return normalize_history_values(sheet.get_all_values()).to_dict("records")


def migrate_history_sheet(store: SheetStore) -> int:
    history_sheet = store.worksheet(LOG_SHEET_NAME, HISTORY_HEADERS)
    raw_values = history_sheet.get_all_values()
    if not raw_values:
        history_sheet.clear()
        history_sheet.append_row(HISTORY_HEADERS)
        return 0

    normalized = normalize_history_values(raw_values)
    if not normalized.empty:
        normalized["Timestamp"] = pd.to_datetime(normalized["Timestamp"], errors="coerce", utc=True)
        normalized = normalized.sort_values(
            ["Timestamp", "Goods ID", "Price", "Listings"], na_position="last"
        )
        normalized = normalized.drop_duplicates(
            subset=["Timestamp", "Goods ID", "Family", "Condition", "Price", "Listings"],
            keep="last",
        )
        normalized["Timestamp"] = normalized["Timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    history_sheet.clear()
    history_sheet.append_row(HISTORY_HEADERS)
    if not normalized.empty:
        history_sheet.append_rows(normalized.values.tolist(), value_input_option="USER_ENTERED")
    return len(normalized)


def load_history_frame(store: SheetStore) -> pd.DataFrame:
    rows = store.history_rows()
    if not rows:
        return pd.DataFrame(columns=HISTORY_HEADERS)
    return pd.DataFrame(rows, columns=HISTORY_HEADERS)


def append_history(store: SheetStore, snapshots: list[MarketSnapshot], timestamp: str) -> None:
    if not snapshots:
        return
    sheet = store.worksheet(LOG_SHEET_NAME, HISTORY_HEADERS)
    rows = [
        [
            timestamp,
            snapshot.goods_id,
            snapshot.family,
            snapshot.knife_type,
            snapshot.skin_name,
            snapshot.condition,
            snapshot.price,
            snapshot.listings,
            snapshot.buy_orders,
            snapshot.reference_price or "",
            snapshot.image_url,
            snapshot.observed_orders,
        ]
        for snapshot in snapshots
    ]
    sheet.append_rows(rows, value_input_option="USER_ENTERED")


def rebuild_catalog(store: SheetStore, snapshots: list[MarketSnapshot]) -> None:
    sheet = store.worksheet(CATALOG_SHEET_NAME, CATALOG_HEADERS)
    sheet.clear()
    sheet.append_row(CATALOG_HEADERS)
    if snapshots:
        sheet.append_rows(
            [
                [
                    snapshot.goods_id,
                    snapshot.family,
                    snapshot.skin_name,
                    snapshot.condition,
                    snapshot.price,
                    snapshot.listings,
                    snapshot.buy_orders,
                    snapshot.reference_price or "",
                    snapshot.image_url,
                ]
                for snapshot in snapshots
            ],
            value_input_option="USER_ENTERED",
        )


def rebuild_all_catalog(store: SheetStore, snapshots: list[MarketSnapshot], timestamp: str) -> None:
    sheet = store.worksheet(ALL_CATALOG_SHEET_NAME, ALL_CATALOG_HEADERS, rows=6000, cols=20)
    sheet.clear()
    sheet.append_row(ALL_CATALOG_HEADERS)
    if not snapshots:
        return
    rows = [
        [
            timestamp,
            snapshot.goods_id,
            snapshot.family,
            snapshot.skin_name,
            snapshot.condition,
            snapshot.price,
            snapshot.listings,
            snapshot.buy_orders,
            snapshot.reference_price or "",
            snapshot.image_url,
            _GOODS_PAGE_URL.format(goods_id=snapshot.goods_id),
        ]
        for snapshot in snapshots
    ]
    sheet.append_rows(rows, value_input_option="USER_ENTERED")


def rebuild_dashboard(store: SheetStore, analysis_rows: list[dict[str, Any]]) -> None:
    headers = [
        "Skin Name",
        "Latest Price",
        "Average Price",
        "Min Price",
        "Max Price",
        "Price Change %",
        "Volatility %",
        "Latest Listings",
        "Listing Pressure %",
        "Signal",
        "Confidence",
    ]
    sheet = store.worksheet(DASHBOARD_SHEET_NAME, headers)
    sheet.clear()
    sheet.append_row(headers)
    if analysis_rows:
        sheet.append_rows(
            [
                [
                    row["skin_name"],
                    row["latest_price"],
                    row["average_price"],
                    row["min_price"],
                    row["max_price"],
                    row["price_change_pct"],
                    row["volatility_pct"],
                    row["latest_listings"],
                    row["listing_pressure_pct"],
                    row["signal"],
                    row["confidence"],
                ]
                for row in analysis_rows
            ],
            value_input_option="USER_ENTERED",
        )


def rebuild_signals(store: SheetStore, analysis_rows: list[dict[str, Any]], timestamp: str) -> None:
    headers = ["Timestamp", "Skin Name", "Signal", "Confidence", "Rationale", "Data Points"]
    sheet = store.worksheet(SIGNALS_SHEET_NAME, headers)
    sheet.clear()
    sheet.append_row(headers)
    if analysis_rows:
        sheet.append_rows(
            [
                [
                    timestamp,
                    row["skin_name"],
                    row["signal"],
                    row["confidence"],
                    row["rationale"],
                    row["data_points"],
                ]
                for row in analysis_rows
            ],
            value_input_option="USER_ENTERED",
        )


def rebuild_forecast(store: SheetStore, history: pd.DataFrame) -> None:
    try:
        from statsmodels.tsa.arima.model import ARIMA
        from statsmodels.tsa.statespace.sarimax import SARIMAX
    except Exception:
        print("Forecast skipped: statsmodels is not installed.")
        return

    headers = ["Skin Name", "Forecast Date", "Predicted Price", "Predicted Listings", "Model"]
    sheet = store.worksheet(FORECAST_SHEET_NAME, headers, rows=800, cols=10)
    sheet.clear()
    sheet.append_row(headers)
    if history.empty:
        return

    prepared = history.copy()
    prepared["Timestamp"] = pd.to_datetime(prepared["Timestamp"], errors="coerce", utc=True)
    prepared["Price"] = pd.to_numeric(prepared["Price"], errors="coerce")
    prepared["Listings"] = pd.to_numeric(prepared.get("Listings"), errors="coerce")
    prepared = prepared.dropna(subset=["Timestamp", "Skin Name", "Price", "Listings"])

    forecast_rows: list[list[Any]] = []
    for skin_name, skin_df in prepared.groupby("Skin Name"):
        skin_df = skin_df.sort_values("Timestamp").copy()
        if len(skin_df) < 10:
            continue

        daily = (
            skin_df.set_index("Timestamp")[["Price", "Listings"]]
            .resample("D")
            .agg({"Price": "mean", "Listings": "last"})
            .dropna()
        )
        if len(daily) < 8:
            continue

        y_price = daily["Price"].astype(float).values
        y_listings = daily["Listings"].astype(float).values

        try:
            listings_model = ARIMA(y_listings, order=(1, 1, 1))
            listings_fitted = listings_model.fit()
            listings_forecast = listings_fitted.forecast(steps=7)
            listings_forecast = [max(0, int(round(float(value)))) for value in listings_forecast]

            price_model = SARIMAX(
                y_price,
                exog=y_listings,
                order=(1, 1, 1),
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
            price_fitted = price_model.fit(disp=False)
            future_exog = pd.Series(listings_forecast, dtype=float).values
            price_forecast = price_fitted.get_forecast(steps=7, exog=future_exog).predicted_mean
            model_name = "SARIMAX(price~listings)+ARIMA(listings)"
        except Exception as exc:
            try:
                price_model = ARIMA(y_price, order=(1, 1, 1))
                price_fitted = price_model.fit()
                price_forecast = price_fitted.forecast(steps=7)
                listings_forecast = [int(round(float(y_listings[-1])))] * 7
                model_name = "ARIMA(price)"
            except Exception as inner_exc:
                print(f"Forecast skipped for {skin_name}: {exc} / fallback failed: {inner_exc}")
                continue

        future_dates = pd.date_range(daily.index.max() + pd.Timedelta(days=1), periods=7, freq="D")
        for forecast_date, predicted_price, predicted_listings in zip(
            future_dates, price_forecast, listings_forecast
        ):
            forecast_rows.append(
                [
                    skin_name,
                    forecast_date.strftime("%Y-%m-%d"),
                    round(float(predicted_price), 2),
                    int(predicted_listings),
                    model_name,
                ]
            )

    if forecast_rows:
        sheet.append_rows(forecast_rows, value_input_option="USER_ENTERED")


def get_track_keywords() -> list[str]:
    raw = os.getenv("BUFF_TRACK_KEYWORDS", ",".join(DEFAULT_TRACK_KEYWORDS))
    return [item.strip() for item in raw.split(",") if item.strip()]


def csgotrader_snapshots(track_keywords: list[str], min_price_cny: float) -> list[MarketSnapshot]:
    usd_to_cny = float(os.getenv("BUFF_USD_CNY", "7.2"))
    response = requests.get(CSGOTRADER_BUFF_URL, timeout=30)
    response.raise_for_status()
    keyword_lower = tuple(keyword.lower() for keyword in track_keywords)
    image_map = csgo_api_image_map() if env_flag("BUFF_FILL_IMAGES", True) else {}
    fill_images = env_flag("BUFF_FILL_STEAM_IMAGES", False)
    image_cache = load_json_file(STEAM_IMAGE_CACHE_PATH) if fill_images else {}
    snapshots: list[MarketSnapshot] = []
    for market_hash_name, value in response.json().items():
        market_hash_name = str(market_hash_name).replace("БЪ", "★")
        clean_name = market_hash_name.replace("★ ", "").strip()
        if not any(keyword in clean_name.lower() for keyword in keyword_lower):
            continue
        family, condition = split_market_name(clean_name)
        starting_at = value.get("starting_at") or {}
        highest_order = value.get("highest_order") or {}
        price_usd = try_float(starting_at.get("price"))
        if price_usd is None:
            continue
        price = price_usd * usd_to_cny
        if price < min_price_cny:
            continue
        image_url = image_map.get(clean_name, "") or image_map.get(family, "")
        if fill_images:
            try:
                image_url = image_url or steam_image_url(str(market_hash_name), image_cache)
            except Exception as exc:
                print(f"Failed Steam image {market_hash_name}: {exc}")
        reference_price_usd = try_float((highest_order or {}).get("price"))
        snapshots.append(
            MarketSnapshot(
                goods_id=source_id("csgotrader", market_hash_name),
                family=family,
                skin_name=(
                    f"{family} ({condition})" if condition and condition not in family else family
                ),
                condition=condition or "Unknown",
                price=price,
                listings=0,
                buy_orders=0,
                reference_price=(
                    reference_price_usd * usd_to_cny if reference_price_usd is not None else None
                ),
                image_url=image_url,
                observed_orders=0,
            )
        )
    if fill_images:
        save_json_file(STEAM_IMAGE_CACHE_PATH, image_cache)
    return sorted(
        snapshots,
        key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
    )
