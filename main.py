from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import gspread
import pandas as pd
import requests
from google.oauth2 import service_account
from requests.adapters import HTTPAdapter
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from urllib3.util.retry import Retry


SHEET_NAME = os.getenv("BUFF_SHEET_NAME", "BuffKnifeTracker")
LOG_SHEET_NAME = "HistoryLog"
CATALOG_SHEET_NAME = "Catalog"
ALL_CATALOG_SHEET_NAME = "AllCatalog"
DASHBOARD_SHEET_NAME = "Dashboard"
FORECAST_SHEET_NAME = "Forecast"
SIGNALS_SHEET_NAME = "Signals"
DEFAULT_BUTTERFLY_SEEDS = ["42552", "42555", "42533", "42587"]
DEFAULT_KARAMBIT_SEEDS = ["42901", "42905", "42911", "42909"]
DEFAULT_TRACK_KEYWORDS = ["Butterfly Knife", "Karambit"]
DEFAULT_SQLITE_PATH = "buff163.sqlite3"

HISTORY_HEADERS = [
    "Timestamp",
    "Goods ID",
    "Family",
    "Knife Type",
    "Skin Name",
    "Condition",
    "Price",
    "Listings",
    "Buy Orders",
    "Reference Price",
    "Image URL",
    "Observed Orders",
]
CATALOG_HEADERS = [
    "Goods ID",
    "Family",
    "Skin Name",
    "Condition",
    "Price",
    "Listings",
    "Buy Orders",
    "Reference Price",
    "Image URL",
]
ALL_CATALOG_HEADERS = [
    "Timestamp",
    "Goods ID",
    "Family",
    "Skin Name",
    "Condition",
    "Price",
    "Listings",
    "Buy Orders",
    "Reference Price",
    "Image URL",
    "Goods URL",
]

QUALITY_MAP = {
    "崭新出厂": "Factory New",
    "略有磨损": "Minimal Wear",
    "久经沙场": "Field-Tested",
    "破损不堪": "Well-Worn",
    "战痕累累": "Battle-Scarred",
    "★ StatTrak™": "StatTrak",
    "StatTrak™": "StatTrak",
}
CONDITION_ORDER = {
    "Factory New": 0,
    "Minimal Wear": 1,
    "Field-Tested": 2,
    "Well-Worn": 3,
    "Battle-Scarred": 4,
    "StatTrak": 5,
    "Unknown": 99,
}


@dataclass(frozen=True)
class MarketSnapshot:
    goods_id: str
    family: str
    skin_name: str
    condition: str
    price: float
    listings: int
    buy_orders: int
    reference_price: float | None
    image_url: str
    observed_orders: int

    @property
    def knife_type(self) -> str:
        return self.family.split("|")[0].replace("★", "").strip()


class BuffPriceClient:
    SELL_ORDER_URL = "https://buff.163.com/api/market/goods/sell_order"
    GOODS_MARKET_URL = "https://buff.163.com/api/market/goods"
    GOODS_PAGE_URL = "https://buff.163.com/goods/{goods_id}?from=market#tab=selling"

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.page_cache: dict[str, dict[str, Any]] = {}
        retry = Retry(
            total=2,
            backoff_factor=0.7,
            status_forcelist=(500, 502, 503, 504),
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

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        max_attempts = 5
        for attempt in range(max_attempts):
            response = self.session.get(url, timeout=self.timeout, **kwargs)
            if response.status_code != 429:
                return response
            backoff_seconds = min(2.0 + attempt * 1.5, 8.0)
            time.sleep(backoff_seconds)
        return response

    def fetch_sell_snapshot(self, goods_id: str, page_meta: dict[str, Any] | None = None) -> MarketSnapshot:
        response = self._get(
            self.SELL_ORDER_URL,
            params={
                "game": "csgo",
                "goods_id": goods_id,
                "page_num": 1,
                "sort_by": "default",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "OK":
            raise ValueError(f"BUFF API returned error code: {payload.get('code')}")

        data = payload.get("data") or {}
        items = data.get("items") or []
        goods_infos = data.get("goods_infos") or {}
        info = goods_infos.get(str(goods_id)) or {}
        if not items or not info:
            raise ValueError("BUFF API returned no sell orders.")

        page_meta = page_meta or self.fetch_goods_page_metadata(goods_id)
        market_hash_name = info.get("market_hash_name") or info.get("name") or f"Goods {goods_id}"
        family, condition = split_market_name(market_hash_name)

        return MarketSnapshot(
            goods_id=str(goods_id),
            family=family,
            skin_name=f"{family} ({condition})" if condition and condition not in family else family,
            condition=condition or "Unknown",
            price=float(items[0]["price"]),
            listings=int(page_meta.get("sell_num") or data.get("total_count") or len(items)),
            buy_orders=int(page_meta.get("buy_num") or 0),
            reference_price=try_float(info.get("steam_price_cny")),
            image_url=(
                info.get("icon_url")
                or info.get("original_icon_url")
                or page_meta.get("icon_url")
                or page_meta.get("image_url")
                or ""
            ),
            observed_orders=len(items),
        )

    def fetch_goods_page_metadata(self, goods_id: str) -> dict[str, Any]:
        goods_id = str(goods_id)
        if goods_id in self.page_cache:
            return self.page_cache[goods_id]

        response = self._get(self.GOODS_PAGE_URL.format(goods_id=goods_id))
        response.raise_for_status()
        page = response.text

        goods_info_match = re.search(r"var goods_info = (\{.*?\})\s*market_show\.pre_init", page, re.DOTALL)
        page_info: dict[str, Any] = {}
        if goods_info_match:
            page_info = json.loads(goods_info_match.group(1))
        image_match = re.search(r'<meta property="og:image" content="([^"]+)"', page)
        if image_match:
            page_info["image_url"] = image_match.group(1)

        top_segment_end = page.find('<div class="market-header black"')
        top_segment = page[:top_segment_end] if top_segment_end != -1 else page
        variant_ids: list[str] = []
        for match in re.finditer(
            r'<a class="[^"]*i_Btn[^"]*"[^>]*data-goodsid="(\d+)"[^>]*>(.*?)</a>',
            top_segment,
            re.DOTALL,
        ):
            inner_text = clean_html_text(match.group(2))
            if inner_text:
                variant_ids.append(match.group(1))

        page_info["variant_goods_ids"] = sorted(set(variant_ids + [goods_id]))
        self.page_cache[goods_id] = page_info
        return page_info

    def discover_butterfly_catalog(self, seed_goods_ids: list[str]) -> list[MarketSnapshot]:
        queue = [str(goods_id) for goods_id in seed_goods_ids]
        seen: set[str] = set()
        snapshots: dict[str, MarketSnapshot] = {}

        while queue:
            goods_id = queue.pop(0)
            if goods_id in seen:
                continue
            seen.add(goods_id)

            try:
                page_info = self.fetch_goods_page_metadata(goods_id)
            except Exception as exc:
                print(f"Failed to parse goods page {goods_id}: {exc}")
                continue

            for variant_id in page_info.get("variant_goods_ids", []):
                if variant_id not in seen and variant_id not in queue:
                    queue.append(variant_id)

            try:
                snapshot = self.fetch_sell_snapshot(goods_id, page_meta=page_info)
            except Exception as exc:
                print(f"Failed to fetch goods {goods_id}: {exc}")
                continue

            if "Butterfly Knife" in snapshot.family:
                snapshots[goods_id] = snapshot
            time.sleep(0.35)

        return sorted(snapshots.values(), key=lambda item: (item.family, item.condition, item.goods_id))

    def discover_high_value_catalog(
        self,
        *,
        keywords: list[str],
        min_price: float,
        seed_goods_ids: list[str] | None = None,
        max_pages_per_keyword: int = 20,
    ) -> list[MarketSnapshot]:
        queue = [str(goods_id) for goods_id in (seed_goods_ids or []) if str(goods_id).strip()]
        for keyword in keywords:
            queue.extend(self.discover_goods_ids_from_market(keyword=keyword, max_pages=max_pages_per_keyword))
        queue = sorted(set(queue))

        seen: set[str] = set()
        snapshots: dict[str, MarketSnapshot] = {}
        keyword_lower = tuple(keyword.lower() for keyword in keywords)

        while queue:
            goods_id = queue.pop(0)
            if goods_id in seen:
                continue
            seen.add(goods_id)

            try:
                page_info = self.fetch_goods_page_metadata(goods_id)
            except Exception as exc:
                print(f"Failed to parse goods page {goods_id}: {exc}")
                continue

            for variant_id in page_info.get("variant_goods_ids", []):
                if variant_id not in seen and variant_id not in queue:
                    queue.append(variant_id)

            try:
                snapshot = self.fetch_sell_snapshot(goods_id, page_meta=page_info)
            except Exception as exc:
                print(f"Failed to fetch goods {goods_id}: {exc}")
                continue

            family_lower = snapshot.family.lower()
            if snapshot.price >= min_price and any(keyword in family_lower for keyword in keyword_lower):
                snapshots[goods_id] = snapshot
            time.sleep(0.35)

        return sorted(
            snapshots.values(),
            key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
        )

    def discover_full_catalog(
        self,
        *,
        keywords: list[str],
        seed_goods_ids: list[str] | None = None,
        max_pages_per_keyword: int = 60,
    ) -> list[MarketSnapshot]:
        queue = [str(goods_id) for goods_id in (seed_goods_ids or []) if str(goods_id).strip()]
        for keyword in keywords:
            queue.extend(self.discover_goods_ids_from_market(keyword=keyword, max_pages=max_pages_per_keyword))
        queue = sorted(set(queue))

        seen: set[str] = set()
        snapshots: dict[str, MarketSnapshot] = {}
        keyword_lower = tuple(keyword.lower() for keyword in keywords)

        while queue:
            goods_id = queue.pop(0)
            if goods_id in seen:
                continue
            seen.add(goods_id)

            try:
                page_info = self.fetch_goods_page_metadata(goods_id)
            except Exception as exc:
                print(f"Failed to parse goods page {goods_id}: {exc}")
                continue

            for variant_id in page_info.get("variant_goods_ids", []):
                if variant_id not in seen and variant_id not in queue:
                    queue.append(variant_id)

            try:
                snapshot = self.fetch_sell_snapshot(goods_id, page_meta=page_info)
            except Exception as exc:
                print(f"Failed to fetch goods {goods_id}: {exc}")
                continue

            family_lower = snapshot.family.lower()
            if any(keyword in family_lower for keyword in keyword_lower):
                snapshots[goods_id] = snapshot
            time.sleep(0.25)

        return sorted(
            snapshots.values(),
            key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
        )

    def discover_goods_ids_from_market(self, *, keyword: str, max_pages: int = 20) -> list[str]:
        goods_ids: set[str] = set()
        for page_num in range(1, max_pages + 1):
            response = self._get(
                self.GOODS_MARKET_URL,
                params={
                    "game": "csgo",
                    "search": keyword,
                    "page_num": page_num,
                    "page_size": 80,
                    "sort_by": "price.desc",
                    "sort_order": "desc",
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != "OK":
                break
            data = payload.get("data") or {}
            items = data.get("items") or []
            if not items:
                break

            for item in items:
                goods_id = item.get("id") or item.get("goods_id")
                if goods_id:
                    goods_ids.add(str(goods_id))

            total_page = int(data.get("total_page") or 0)
            if total_page and page_num >= total_page:
                break
            time.sleep(0.2)

        return sorted(goods_ids)


class SheetStore:
    def __init__(self, sheet_name: str) -> None:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = load_google_credentials(scope)
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open(sheet_name)

    def worksheet(self, title: str, headers: list[str], rows: int = 2000, cols: int = 20):
        try:
            sheet = self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            sheet = self.spreadsheet.add_worksheet(title=title, rows=str(rows), cols=str(cols))
            sheet.append_row(headers)
        return sheet

    def history_rows(self) -> list[dict[str, Any]]:
        sheet = self.worksheet(LOG_SHEET_NAME, HISTORY_HEADERS)
        return normalize_history_values(sheet.get_all_values()).to_dict("records")


def sqlite_connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def sqlite_init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS goods (
            goods_id TEXT PRIMARY KEY,
            family TEXT NOT NULL,
            knife_type TEXT NOT NULL,
            skin_name TEXT NOT NULL,
            condition TEXT NOT NULL,
            reference_price REAL,
            image_url TEXT
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            goods_id TEXT NOT NULL REFERENCES goods(goods_id) ON DELETE CASCADE,
            price REAL NOT NULL,
            listings INTEGER NOT NULL,
            buy_orders INTEGER NOT NULL,
            observed_orders INTEGER NOT NULL,
            UNIQUE(ts, goods_id)
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_goods_ts ON snapshots(goods_id, ts);
        CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
        """
    )


def sqlite_upsert_snapshot(
    conn: sqlite3.Connection,
    *,
    timestamp: str,
    snapshot: MarketSnapshot,
) -> None:
    conn.execute(
        """
        INSERT INTO goods(goods_id, family, knife_type, skin_name, condition, reference_price, image_url)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(goods_id) DO UPDATE SET
            family=excluded.family,
            knife_type=excluded.knife_type,
            skin_name=excluded.skin_name,
            condition=excluded.condition,
            reference_price=excluded.reference_price,
            image_url=excluded.image_url;
        """,
        (
            snapshot.goods_id,
            snapshot.family,
            snapshot.knife_type,
            snapshot.skin_name,
            snapshot.condition,
            snapshot.reference_price,
            snapshot.image_url,
        ),
    )
    conn.execute(
        """
        INSERT INTO snapshots(ts, goods_id, price, listings, buy_orders, observed_orders)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(ts, goods_id) DO UPDATE SET
            price=excluded.price,
            listings=excluded.listings,
            buy_orders=excluded.buy_orders,
            observed_orders=excluded.observed_orders;
        """,
        (
            timestamp,
            snapshot.goods_id,
            snapshot.price,
            snapshot.listings,
            snapshot.buy_orders,
            snapshot.observed_orders,
        ),
    )


def sqlite_write_snapshots(db_path: str, snapshots: list[MarketSnapshot], timestamp: str) -> None:
    if not snapshots:
        return
    conn = sqlite_connect(db_path)
    try:
        sqlite_init(conn)
        with conn:
            for snapshot in snapshots:
                sqlite_upsert_snapshot(conn, timestamp=timestamp, snapshot=snapshot)
    finally:
        conn.close()


def sqlite_load_history_frame(db_path: str) -> pd.DataFrame:
    if not Path(db_path).exists():
        return pd.DataFrame(columns=HISTORY_HEADERS)
    conn = sqlite_connect(db_path)
    try:
        query = """
        SELECT
            s.ts AS "Timestamp",
            g.goods_id AS "Goods ID",
            g.family AS "Family",
            g.knife_type AS "Knife Type",
            g.skin_name AS "Skin Name",
            g.condition AS "Condition",
            s.price AS "Price",
            s.listings AS "Listings",
            s.buy_orders AS "Buy Orders",
            g.reference_price AS "Reference Price",
            g.image_url AS "Image URL",
            s.observed_orders AS "Observed Orders"
        FROM snapshots s
        JOIN goods g ON g.goods_id = s.goods_id
        ORDER BY s.ts ASC;
        """
        frame = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    return frame.reindex(columns=HISTORY_HEADERS)


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
        avg_price = mean(prices)
        min_price = min(prices)
        max_price = max(prices)
        price_stddev = pstdev(prices) if len(prices) > 1 else 0.0
        volatility_pct = (price_stddev / avg_price * 100) if avg_price else 0.0
        price_change_pct = ((latest_price - baseline_price) / baseline_price * 100) if baseline_price else 0.0
        listing_avg = mean(listings)
        latest_listings = listings[-1]
        listing_pressure_pct = ((latest_listings - listing_avg) / listing_avg * 100) if listing_avg else 0.0

        signal, confidence, rationale = self._classify(
            latest_price=latest_price,
            avg_price=avg_price,
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

        if undervalued and listing_spike:
            return ("BUY_WATCH", 0.79, "Price is below its average while stock is elevated.")
        if overvalued and listing_drop:
            return ("SELL_WATCH", 0.76, "Price is above its average while sell-side stock is tightening.")
        if near_floor:
            return ("ACCUMULATE", 0.67, "Price is near the observed floor for this condition.")
        if near_ceiling:
            return ("TAKE_PROFIT", 0.66, "Price is near the observed ceiling for this condition.")
        if volatility_pct >= 8:
            return ("HIGH_VOLATILITY", 0.58, "Price swings are elevated relative to the average.")
        return ("HOLD", 0.45, "Current price and listing depth are near the recent baseline.")


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

    raise FileNotFoundError("credentials.json was not found.")


def credentials_from_info(info: dict[str, Any], scope: list[str]) -> service_account.Credentials:
    normalized = dict(info)
    private_key = normalized.get("private_key")
    if isinstance(private_key, str):
        normalized["private_key"] = private_key.replace("\\n", "\n").replace("\r\n", "\n")
    return service_account.Credentials.from_service_account_info(normalized, scopes=scope)


def load_google_credentials(scope: list[str]) -> service_account.Credentials:
    env_json_keys = [
        "GSHEET_CREDS_JSON",
        "GSHEET_CREDS",
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
        "GOOGLE_CREDENTIALS_JSON",
    ]
    for key in env_json_keys:
        raw_json = os.getenv(key)
        if raw_json:
            return credentials_from_info(json.loads(raw_json), scope)

    try:
        import streamlit as st

        for key in ("GSHEET_CREDS_JSON", "GSHEET_CREDS", "GOOGLE_CREDENTIALS_JSON"):
            if key in st.secrets:
                return credentials_from_info(json.loads(str(st.secrets[key])), scope)
        if "gcp_service_account" in st.secrets:
            return credentials_from_info(dict(st.secrets["gcp_service_account"]), scope)
    except Exception:
        pass

    return service_account.Credentials.from_service_account_file(
        str(resolve_credentials_path()),
        scopes=scope,
    )


def try_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def split_market_name(name: str) -> tuple[str, str]:
    cleaned = name.replace("★ ", "").strip()
    match = re.match(r"(.+?) \((.+)\)$", cleaned)
    if not match:
        return cleaned, ""
    return match.group(1).strip(), match.group(2).strip()


def canonicalize_family_name(name: str) -> str:
    value = (name or "").strip().replace("★ ", "")
    if value.startswith("Butterfly | "):
        return value.replace("Butterfly | ", "Butterfly Knife | ", 1)
    if value.startswith("StatTrak™ Butterfly | "):
        return value.replace("StatTrak™ Butterfly | ", "StatTrak™ Butterfly Knife | ", 1)
    return value


def clean_html_text(raw_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    for cn, en in QUALITY_MAP.items():
        text = text.replace(cn, en)
    return text


def parse_family_and_condition(row: dict[str, Any]) -> tuple[str, str]:
    family = str(row.get("Family") or "").strip()
    condition = str(row.get("Condition") or "").strip()
    skin_name = str(row.get("Skin Name") or "").strip()
    family = canonicalize_family_name(family)
    skin_name = canonicalize_family_name(skin_name)
    if family and condition:
        return family, condition
    if skin_name:
        derived_family, derived_condition = split_market_name(skin_name)
        return canonicalize_family_name(family or derived_family), condition or derived_condition
    return family, condition


def normalize_history_values(raw_values: list[list[Any]]) -> pd.DataFrame:
    if not raw_values:
        return pd.DataFrame(columns=HISTORY_HEADERS)

    headers = [str(cell).strip() for cell in raw_values[0]]
    rows = raw_values[1:]

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
    family_idx = find_index("Family")
    knife_type_idx = find_index("Knife Type", "Knife")
    skin_name_idx = find_index("Skin Name", "Skin")
    condition_idx = find_index("Condition")
    price_idx = find_index("Price")
    listings_idx = find_index("Listings", "Sell Listings")
    buy_orders_idx = find_index("Buy Orders", "Buy Order")
    reference_price_idx = find_index("Reference Price", "Steam Price")
    image_url_idx = find_index("Image URL", "Icon URL")
    observed_orders_idx = find_index("Observed Orders", "Sample Size", "Observed")

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not any(str(cell).strip() for cell in row):
            continue

        def cell(idx: int | None) -> str:
            if idx is None or idx >= len(row):
                return ""
            return str(row[idx]).strip()

        normalized = {
            "Timestamp": cell(timestamp_idx),
            "Goods ID": cell(goods_id_idx),
            "Family": cell(family_idx),
            "Knife Type": cell(knife_type_idx),
            "Skin Name": cell(skin_name_idx),
            "Condition": cell(condition_idx),
            "Price": cell(price_idx).replace(",", "."),
            "Listings": cell(listings_idx),
            "Buy Orders": cell(buy_orders_idx),
            "Reference Price": cell(reference_price_idx),
            "Image URL": cell(image_url_idx),
            "Observed Orders": cell(observed_orders_idx),
        }
        family, condition = parse_family_and_condition(normalized)
        normalized["Family"] = family
        normalized["Condition"] = condition
        if not normalized["Knife Type"] and family:
            normalized["Knife Type"] = family.split("|")[0].strip()
        if family and condition:
            normalized["Skin Name"] = f"{family} ({condition})"
        elif family:
            normalized["Skin Name"] = family
        normalized_rows.append(normalized)

    return pd.DataFrame(normalized_rows, columns=HISTORY_HEADERS)


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
        normalized = normalized.sort_values(["Timestamp", "Goods ID", "Price", "Listings"], na_position="last")
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
            BuffPriceClient.GOODS_PAGE_URL.format(goods_id=snapshot.goods_id),
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
        for forecast_date, predicted_price, predicted_listings in zip(future_dates, price_forecast, listings_forecast):
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


def get_seed_goods_ids() -> list[str]:
    raw = os.getenv("BUFF_SEED_GOODS_IDS")
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    legacy_raw = os.getenv("BUFF_BUTTERFLY_SEEDS")
    if legacy_raw:
        return [item.strip() for item in legacy_raw.split(",") if item.strip()]
    raw = ",".join(DEFAULT_BUTTERFLY_SEEDS + DEFAULT_KARAMBIT_SEEDS)
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_track_keywords() -> list[str]:
    raw = os.getenv("BUFF_TRACK_KEYWORDS", ",".join(DEFAULT_TRACK_KEYWORDS))
    return [item.strip() for item in raw.split(",") if item.strip()]


def run(migrate_only: bool = False) -> None:
    store = SheetStore(SHEET_NAME)
    migrated_rows = migrate_history_sheet(store)
    if migrated_rows:
        print(f"Migrated {migrated_rows} history rows to the current schema.")

    history = load_history_frame(store)
    if migrate_only:
        agent = PriceAnalysisAgent(history)
        tracked_names = sorted(history["Skin Name"].dropna().unique().tolist())
        analysis_rows = [summary for name in tracked_names if (summary := agent.summarize_skin(name))]
        rebuild_dashboard(store, analysis_rows)
        rebuild_signals(store, analysis_rows, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        rebuild_forecast(store, history)
        print("Migration-only run completed.")
        return

    client = BuffPriceClient()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    min_price = float(os.getenv("BUFF_MIN_PRICE_CNY", "5000"))
    try:
        high_value_pages = max(1, int(os.getenv("BUFF_HIGH_VALUE_PAGES", "60")))
    except ValueError:
        high_value_pages = 60
    track_keywords = get_track_keywords()
    snapshots = client.discover_high_value_catalog(
        keywords=track_keywords,
        min_price=min_price,
        seed_goods_ids=get_seed_goods_ids(),
        max_pages_per_keyword=high_value_pages,
    )

    full_catalog_enabled = os.getenv("BUFF_FULL_CATALOG", "").strip().lower() in {"1", "true", "yes", "on"}
    if full_catalog_enabled:
        max_pages = int(os.getenv("BUFF_FULL_CATALOG_PAGES", "60"))
        full_snapshots = client.discover_full_catalog(
            keywords=track_keywords,
            seed_goods_ids=get_seed_goods_ids(),
            max_pages_per_keyword=max_pages,
        )
        rebuild_all_catalog(store, full_snapshots, timestamp)

    sqlite_path = os.getenv("BUFF_SQLITE_PATH", DEFAULT_SQLITE_PATH).strip()
    enable_sqlite = os.getenv("BUFF_WRITE_SQLITE", "").strip().lower() in {"1", "true", "yes", "on"}
    if enable_sqlite and sqlite_path:
        sqlite_write_snapshots(sqlite_path, snapshots, timestamp)

    rebuild_catalog(store, snapshots)
    append_history(store, snapshots, timestamp)

    history = load_history_frame(store)
    agent = PriceAnalysisAgent(history)
    tracked_names = sorted(set(history["Skin Name"].dropna().unique().tolist()))
    analysis_rows = [summary for name in tracked_names if (summary := agent.summarize_skin(name))]

    rebuild_dashboard(store, analysis_rows)
    rebuild_signals(store, analysis_rows, timestamp)
    rebuild_forecast(store, history)
    print(
        f"Collected {len(snapshots)} high-value snapshots for {', '.join(track_keywords)} "
        f"(>= {min_price:.0f} CNY, pages={high_value_pages})."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--migrate-only", action="store_true")
    args = parser.parse_args()
    try:
        run(migrate_only=args.migrate_only)
    except FileNotFoundError as exc:
        print(f"Startup error: {exc}")
        print(
            "Provide Google credentials via `GSHEET_CREDS_JSON` or place `credentials.json` "
            "in the project root. For local SQLite-only viewing, use Streamlit with "
            "`BUFF_READ_SQLITE=1` and `BUFF_SQLITE_PATH`."
        )
        raise SystemExit(1)
    except Exception as exc:
        print(f"Unhandled error: {exc.__class__.__name__}: {exc}")
        raise SystemExit(1)
