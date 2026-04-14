from __future__ import annotations

import argparse
import math
import os
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import gspread
import pandas as pd
import requests
from oauth2client.service_account import ServiceAccountCredentials
from requests.adapters import HTTPAdapter
from statsmodels.tsa.arima.model import ARIMA
from urllib3.util.retry import Retry


SHEET_NAME = os.getenv("BUFF_SHEET_NAME", "BuffKnifeTracker")
LOG_SHEET_NAME = "HistoryLog"
DASHBOARD_SHEET_NAME = "Dashboard"
FORECAST_SHEET_NAME = "Forecast"
SIGNALS_SHEET_NAME = "Signals"
HISTORY_HEADERS = [
    "Timestamp",
    "Goods ID",
    "Knife Type",
    "Skin Name",
    "Condition",
    "Price",
    "Listings",
    "Observed Orders",
]


@dataclass(frozen=True)
class SkinConfig:
    goods_id: str
    name: str
    condition: str

    @property
    def knife_type(self) -> str:
        return self.name.split(" | ")[0].strip()


SKINS: list[SkinConfig] = [
    SkinConfig(goods_id="42552", name="Butterfly | Damascus Steel", condition="Field-Tested"),
    SkinConfig(goods_id="42555", name="Butterfly | Doppler", condition="Factory New"),
    SkinConfig(goods_id="42998", name="Karambit | Doppler", condition="Factory New"),
    SkinConfig(goods_id="42533", name="Butterfly | Blue Steel", condition="Field-Tested"),
    SkinConfig(goods_id="83578", name="Gloves | Nocts", condition="Field-Tested"),
    SkinConfig(goods_id="42587", name="Butterfly | Tiger Tooth", condition="Factory New"),
]
SKIN_BY_NAME = {skin.name: skin for skin in SKINS}


class BuffPriceClient:
    BASE_URL = "https://buff.163.com/api/market/goods/sell_order"

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(
            total=4,
            backoff_factor=1.2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://buff.163.com/market/csgo",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            }
        )
        cookie = os.getenv("BUFF_COOKIE")
        if cookie:
            self.session.headers["Cookie"] = cookie

    def fetch_sell_snapshot(self, skin: SkinConfig) -> dict[str, Any]:
        params = {
            "game": "csgo",
            "goods_id": skin.goods_id,
            "page_num": 1,
            "sort_by": "default",
        }
        response = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
        response.raise_for_status()

        payload = response.json()
        if payload.get("code") not in (None, "OK") and payload.get("code") != "OK":
            raise ValueError(f"BUFF API returned error code: {payload.get('code')}")

        data = payload.get("data") or {}
        items = data.get("items") or []
        if not items:
            raise ValueError("BUFF API returned no sell orders.")

        best_order = items[0]
        price = float(best_order["price"])
        sell_count = int(data.get("total_count") or len(items))

        return {
            "goods_id": skin.goods_id,
            "knife_type": skin.knife_type,
            "skin_name": skin.name,
            "condition": skin.condition,
            "price": round(price, 2),
            "sell_count": sell_count,
            "sample_size": len(items),
        }


class SheetStore:
    def __init__(self, sheet_name: str) -> None:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = load_google_credentials(scope)
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open(sheet_name)

    def worksheet(self, title: str, headers: list[str], rows: int = 1000, cols: int = 20):
        try:
            sheet = self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            sheet = self.spreadsheet.add_worksheet(title=title, rows=str(rows), cols=str(cols))
            sheet.append_row(headers)
        return sheet

    def history_rows(self) -> list[dict[str, Any]]:
        sheet = self.worksheet(LOG_SHEET_NAME, HISTORY_HEADERS)
        return normalize_history_values(sheet.get_all_values()).to_dict("records")


def resolve_credentials_path() -> Path:
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    candidates = [
        Path("credentials.json"),
        Path(__file__).resolve().parent / "credentials.json",
        Path(__file__).resolve().parent.parent / "credentials.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "credentials.json was not found. Put it next to main.py, one folder above it, or set GOOGLE_APPLICATION_CREDENTIALS."
    )


def load_google_credentials(scope: list[str]) -> ServiceAccountCredentials:
    raw_json = os.getenv("GSHEET_CREDS_JSON")
    if raw_json:
        return ServiceAccountCredentials.from_json_keyfile_dict(json.loads(raw_json), scope)

    raw_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if raw_path:
        return ServiceAccountCredentials.from_json_keyfile_dict(json.loads(raw_path), scope)

    try:
        import streamlit as st

        if "GSHEET_CREDS_JSON" in st.secrets:
            return ServiceAccountCredentials.from_json_keyfile_dict(
                json.loads(st.secrets["GSHEET_CREDS_JSON"]),
                scope,
            )

        if "gcp_service_account" in st.secrets:
            return ServiceAccountCredentials.from_json_keyfile_dict(
                dict(st.secrets["gcp_service_account"]),
                scope,
            )
    except Exception:
        pass

    return ServiceAccountCredentials.from_json_keyfile_name(str(resolve_credentials_path()), scope)


def normalize_history_values(raw_values: list[list[Any]]) -> pd.DataFrame:
    if not raw_values:
        return pd.DataFrame(columns=HISTORY_HEADERS)

    headers = [str(cell).strip() for cell in raw_values[0]]
    rows = raw_values[1:]
    if not headers:
        return pd.DataFrame(columns=HISTORY_HEADERS)

    def find_index(*candidates: str) -> int | None:
        lowered = [header.lower() for header in headers]
        for candidate in candidates:
            candidate_lower = candidate.lower()
            for idx, header in enumerate(lowered):
                if header == candidate_lower:
                    return idx
            for idx, header in enumerate(lowered):
                if candidate_lower in header:
                    return idx
        return None

    timestamp_idx = find_index("Timestamp")
    goods_id_idx = find_index("Goods ID", "GoodsId")
    knife_type_idx = find_index("Knife Type", "Knife")
    skin_name_idx = find_index("Skin Name", "Skin")
    condition_idx = find_index("Condition")
    price_idx = find_index("Price")
    listings_idx = find_index("Listings", "Sell Listings")
    observed_orders_idx = find_index("Observed Orders", "Sample Size", "Observed")

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not any(str(cell).strip() for cell in row):
            continue

        def cell(idx: int | None) -> str:
            if idx is None or idx >= len(row):
                return ""
            return str(row[idx]).strip()

        skin_name = cell(skin_name_idx)
        skin_config = SKIN_BY_NAME.get(skin_name)
        knife_type = cell(knife_type_idx) or (skin_config.knife_type if skin_config else skin_name.split(" | ")[0].strip())
        normalized_rows.append(
            {
                "Timestamp": cell(timestamp_idx),
                "Goods ID": cell(goods_id_idx) or (skin_config.goods_id if skin_config else ""),
                "Knife Type": knife_type,
                "Skin Name": skin_name,
                "Condition": cell(condition_idx) or (skin_config.condition if skin_config else ""),
                "Price": cell(price_idx).replace(",", "."),
                "Listings": cell(listings_idx),
                "Observed Orders": cell(observed_orders_idx),
            }
        )

    return pd.DataFrame(normalized_rows, columns=HISTORY_HEADERS)


def migrate_history_sheet(store: SheetStore) -> int:
    history_sheet = store.worksheet(LOG_SHEET_NAME, HISTORY_HEADERS)
    raw_values = history_sheet.get_all_values()

    if not raw_values:
        history_sheet.clear()
        history_sheet.append_row(HISTORY_HEADERS)
        return 0

    current_headers = [str(cell).strip() for cell in raw_values[0]]
    normalized = normalize_history_values(raw_values)

    if current_headers == HISTORY_HEADERS and len(normalized) == max(len(raw_values) - 1, 0):
        return 0

    history_sheet.clear()
    history_sheet.append_row(HISTORY_HEADERS)
    if not normalized.empty:
        history_sheet.append_rows(normalized.values.tolist(), value_input_option="USER_ENTERED")
    return len(normalized)


class PriceAnalysisAgent:
    def __init__(self, history: pd.DataFrame) -> None:
        self.history = history.copy()
        if not self.history.empty:
            self.history["Timestamp"] = pd.to_datetime(self.history["Timestamp"], errors="coerce", utc=True)
            self.history["Price"] = pd.to_numeric(self.history["Price"], errors="coerce")
            self.history["Listings"] = pd.to_numeric(self.history["Listings"], errors="coerce")
            self.history = self.history.dropna(subset=["Timestamp", "Skin Name", "Price", "Listings"])

    def summarize_skin(self, skin_name: str) -> dict[str, Any] | None:
        skin_history = self.history[self.history["Skin Name"] == skin_name].sort_values("Timestamp")
        if skin_history.empty:
            return None

        prices = skin_history["Price"].tolist()
        listings = skin_history["Listings"].tolist()
        latest_price = prices[-1]
        baseline_price = mean(prices[:-1]) if len(prices) > 1 else latest_price
        min_price = min(prices)
        max_price = max(prices)
        avg_price = mean(prices)
        price_stddev = pstdev(prices) if len(prices) > 1 else 0.0
        volatility_pct = (price_stddev / avg_price * 100) if avg_price else 0.0
        price_change_pct = ((latest_price - baseline_price) / baseline_price * 100) if baseline_price else 0.0

        recent_window = prices[-3:] if len(prices) >= 3 else prices
        short_term_avg = mean(recent_window)
        listing_avg = mean(listings)
        latest_listings = listings[-1]
        listing_pressure_pct = ((latest_listings - listing_avg) / listing_avg * 100) if listing_avg else 0.0

        signal, confidence, rationale = self._classify(
            latest_price=latest_price,
            avg_price=avg_price,
            short_term_avg=short_term_avg,
            min_price=min_price,
            max_price=max_price,
            latest_listings=latest_listings,
            listing_avg=listing_avg,
            volatility_pct=volatility_pct,
        )

        return {
            "skin_name": skin_name,
            "latest_price": round(latest_price, 2),
            "average_price": round(avg_price, 2),
            "min_price": round(min_price, 2),
            "max_price": round(max_price, 2),
            "price_change_pct": round(price_change_pct, 2),
            "volatility_pct": round(volatility_pct, 2),
            "latest_listings": int(latest_listings),
            "listing_pressure_pct": round(listing_pressure_pct, 2),
            "signal": signal,
            "confidence": round(confidence, 2),
            "rationale": rationale,
            "data_points": len(prices),
        }

    def _classify(
        self,
        *,
        latest_price: float,
        avg_price: float,
        short_term_avg: float,
        min_price: float,
        max_price: float,
        latest_listings: float,
        listing_avg: float,
        volatility_pct: float,
    ) -> tuple[str, float, str]:
        undervalued = latest_price < avg_price * 0.97
        overvalued = latest_price > avg_price * 1.03
        listing_spike = latest_listings > listing_avg * 1.1 if listing_avg else False
        listing_drop = latest_listings < listing_avg * 0.9 if listing_avg else False
        near_floor = math.isclose(latest_price, min_price, rel_tol=0.01) or latest_price <= min_price * 1.03
        near_ceiling = math.isclose(latest_price, max_price, rel_tol=0.01) or latest_price >= max_price * 0.97

        confidence = 0.45
        if undervalued and listing_spike:
            confidence = 0.79
            return (
                "BUY_WATCH",
                confidence,
                "Price is below its historical average while listings are elevated, which can signal short-term oversupply.",
            )
        if overvalued and listing_drop:
            confidence = 0.76
            return (
                "SELL_WATCH",
                confidence,
                "Price is above its historical average and listings are tightening, which can indicate a stretched market.",
            )
        if near_floor and latest_price <= short_term_avg:
            confidence = 0.67
            return (
                "ACCUMULATE",
                confidence,
                "Price is trading near the lower end of its observed range without overheating above the recent average.",
            )
        if near_ceiling and latest_price >= short_term_avg:
            confidence = 0.66
            return (
                "TAKE_PROFIT",
                confidence,
                "Price is near the top of the observed range and already above the recent average.",
            )
        if volatility_pct >= 8:
            confidence = 0.58
            return (
                "HIGH_VOLATILITY",
                confidence,
                "Price swings are elevated, so waiting for a cleaner setup is safer than reacting to one snapshot.",
            )
        return (
            "HOLD",
            confidence,
            "Current price and listing depth are close to their recent baseline, so there is no strong edge yet.",
        )


def load_history_frame(store: SheetStore) -> pd.DataFrame:
    rows = store.history_rows()
    if not rows:
        return pd.DataFrame(columns=HISTORY_HEADERS)
    return pd.DataFrame(rows, columns=HISTORY_HEADERS)


def append_history(store: SheetStore, snapshots: list[dict[str, Any]], timestamp: str) -> None:
    if not snapshots:
        return

    sheet = store.worksheet(
        LOG_SHEET_NAME,
        HISTORY_HEADERS,
    )
    rows = [
        [
            timestamp,
            snapshot["goods_id"],
            snapshot["knife_type"],
            snapshot["skin_name"],
            snapshot["condition"],
            snapshot["price"],
            snapshot["sell_count"],
            snapshot["sample_size"],
        ]
        for snapshot in snapshots
    ]
    sheet.append_rows(rows, value_input_option="USER_ENTERED")


def rebuild_dashboard(store: SheetStore, analysis_rows: list[dict[str, Any]]) -> None:
    dashboard = store.worksheet(
        DASHBOARD_SHEET_NAME,
        [
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
        ],
    )
    dashboard.clear()
    dashboard.append_row(
        [
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
    )
    if analysis_rows:
        dashboard.append_rows(
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
    signals = store.worksheet(
        SIGNALS_SHEET_NAME,
        [
            "Timestamp",
            "Skin Name",
            "Signal",
            "Confidence",
            "Rationale",
            "Data Points",
        ],
    )
    signals.clear()
    signals.append_row(
        ["Timestamp", "Skin Name", "Signal", "Confidence", "Rationale", "Data Points"]
    )
    if analysis_rows:
        signals.append_rows(
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
    forecast_sheet = store.worksheet(
        FORECAST_SHEET_NAME,
        ["Skin Name", "Forecast Date", "Predicted Price"],
        rows=500,
        cols=10,
    )
    forecast_sheet.clear()
    forecast_sheet.append_row(["Skin Name", "Forecast Date", "Predicted Price"])

    if history.empty:
        return

    prepared = history.copy()
    prepared["Timestamp"] = pd.to_datetime(prepared["Timestamp"], errors="coerce", utc=True)
    prepared["Price"] = pd.to_numeric(prepared["Price"], errors="coerce")
    prepared = prepared.dropna(subset=["Timestamp", "Skin Name", "Price"])

    forecast_rows: list[list[Any]] = []
    for skin_name, skin_df in prepared.groupby("Skin Name"):
        skin_df = skin_df.sort_values("Timestamp")
        if len(skin_df) < 6:
            continue

        try:
            model = ARIMA(skin_df["Price"].values, order=(1, 1, 1))
            fitted = model.fit()
            forecast = fitted.forecast(steps=7)
            future_dates = pd.date_range(
                start=skin_df["Timestamp"].iloc[-1] + pd.Timedelta(days=1),
                periods=7,
                freq="D",
            )
            for forecast_date, predicted_price in zip(future_dates, forecast):
                forecast_rows.append(
                    [skin_name, forecast_date.strftime("%Y-%m-%d"), round(float(predicted_price), 2)]
                )
        except Exception as exc:
            print(f"Forecast skipped for {skin_name}: {exc}")

    if forecast_rows:
        forecast_sheet.append_rows(forecast_rows, value_input_option="USER_ENTERED")


def run(migrate_only: bool = False) -> None:
    store = SheetStore(SHEET_NAME)
    migrated_rows = migrate_history_sheet(store)
    if migrated_rows:
        print(f"Migrated {migrated_rows} existing history rows to the new schema.")

    if migrate_only:
        history = load_history_frame(store)
        agent = PriceAnalysisAgent(history)
        analysis_rows = [summary for skin in SKINS if (summary := agent.summarize_skin(skin.name))]
        rebuild_dashboard(store, analysis_rows)
        rebuild_signals(store, analysis_rows, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        rebuild_forecast(store, history)
        print("Migration-only run completed.")
        return

    client = BuffPriceClient()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    snapshots: list[dict[str, Any]] = []
    for skin in SKINS:
        try:
            snapshot = client.fetch_sell_snapshot(skin)
            snapshots.append(snapshot)
            print(
                f"Fetched {skin.name}: {snapshot['price']} CNY with {snapshot['sell_count']} listings."
            )
        except Exception as exc:
            print(f"Failed to fetch {skin.name}: {exc}")

    append_history(store, snapshots, timestamp)

    history = load_history_frame(store)
    agent = PriceAnalysisAgent(history)
    analysis_rows = [summary for skin in SKINS if (summary := agent.summarize_skin(skin.name))]

    rebuild_dashboard(store, analysis_rows)
    rebuild_signals(store, analysis_rows, timestamp)
    rebuild_forecast(store, history)

    print(f"Updated {len(snapshots)} skins, {len(analysis_rows)} analysis rows, and forecast output.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--migrate-only",
        action="store_true",
        help="Convert old Google Sheet history rows to the new schema without fetching live prices.",
    )
    args = parser.parse_args()
    run(migrate_only=args.migrate_only)
