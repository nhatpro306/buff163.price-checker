from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import time
from http.cookies import SimpleCookie
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import gspread
import pandas as pd
import requests
from google.oauth2 import service_account
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from market_config import (
    ALL_CATALOG_HEADERS,
    ALL_CATALOG_SHEET_NAME,
    CATALOG_HEADERS,
    CATALOG_SHEET_NAME,
    CONDITION_ORDER,
    CSGOTRADER_BUFF_URL,
    DASHBOARD_SHEET_NAME,
    DEFAULT_KNIFE_CATEGORIES,
    DEFAULT_KNIFE_FINISHES,
    DEFAULT_SQLITE_PATH,
    DEFAULT_TRACK_KEYWORDS,
    FORECAST_SHEET_NAME,
    HISTORY_HEADERS,
    LOG_SHEET_NAME,
    SHEET_NAME,
    SIGNALS_SHEET_NAME,
    STEAM_IMAGE_CACHE_PATH,
)
from market_models import MarketSnapshot
from market_utils import (
    canonicalize_family_name,
    clean_html_text,
    csgo_api_image_map,
    env_flag,
    load_json_file,
    normalize_image_url,
    save_json_file,
    source_id,
    split_market_name,
    steam_image_url,
    try_float,
)

# Note: `src/` modules provide thin re-export wrappers for cleaner imports in
# UI and future modularization without changing tracker runtime behavior here.

class BuffPriceClient:
    SELL_ORDER_URL = "https://buff.163.com/api/market/goods/sell_order"
    GOODS_MARKET_URL = "https://buff.163.com/api/market/goods"
    GOODS_PAGE_URL = "https://buff.163.com/goods/{goods_id}?from=market#tab=selling"

    def __init__(self, timeout: int | None = None) -> None:
        if timeout is None:
            timeout = int(os.getenv("BUFF_REQUEST_TIMEOUT", "20"))
        self.timeout = timeout
        self.session = requests.Session()
        self.page_cache: dict[str, dict[str, Any]] = {}
        # BUFF occasionally has transient server errors. Retry only safe GET
        # requests so a temporary failure does not make the scheduled job fail.
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
            # Some BUFF endpoints return richer or more reliable data with a
            # logged-in browser cookie. Store it in GitHub/Streamlit secrets.
            self.session.headers["Cookie"] = cookie
            parsed_cookie = SimpleCookie()
            try:
                parsed_cookie.load(cookie)
                csrf_token = parsed_cookie.get("csrf_token")
            except Exception:
                csrf_token = None
            if csrf_token:
                self.session.headers["X-CSRFToken"] = csrf_token.value

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        max_attempts = max(1, int(os.getenv("BUFF_MAX_429_ATTEMPTS", "5")))
        for attempt in range(max_attempts):
            response = self.session.get(url, timeout=self.timeout, **kwargs)
            if response.status_code != 429:
                return response
            # 429 means rate-limited. Back off instead of retrying immediately,
            # otherwise BUFF is more likely to keep blocking the workflow.
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
            image_url=normalize_image_url(
                info.get("original_icon_url")
                or info.get("icon_url")
                or page_meta.get("original_icon_url")
                or page_meta.get("icon_url")
                or page_meta.get("image_url")
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
        keywords: list[str | tuple[str, str | None]],
        min_price: float,
        seed_goods_ids: list[str] | None = None,
        max_pages_per_keyword: int = 20,
        match_keywords: list[str] | None = None,
        on_snapshot: Any | None = None,
        max_goods: int | None = None,
    ) -> list[MarketSnapshot]:
        queue = [str(goods_id) for goods_id in (seed_goods_ids or []) if str(goods_id).strip()]
        snapshots: dict[str, MarketSnapshot] = {}
        for query in keywords:
            keyword, category = query if isinstance(query, tuple) else (query, None)
            for snapshot in self.discover_snapshots_from_market(
                keyword=keyword,
                category=category,
                min_price=min_price,
                max_pages=max_pages_per_keyword,
            ):
                snapshots[snapshot.goods_id] = snapshot
                if on_snapshot is not None:
                    on_snapshot(snapshot)
                if max_goods is not None and len(snapshots) >= max_goods:
                    break
            if max_goods is not None and len(snapshots) >= max_goods:
                break
            queue.extend(
                self.discover_goods_ids_from_market(keyword=keyword, category=category, max_pages=0)
            )
        queue = sorted(set(queue))

        seen: set[str] = set()
        keyword_lower = tuple(keyword.lower() for keyword in (match_keywords or keywords))

        while queue:
            if max_goods is not None and len(seen) >= max_goods:
                break
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
                if on_snapshot is not None:
                    on_snapshot(snapshot)
            time.sleep(0.35)

        return sorted(
            snapshots.values(),
            key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
        )

    def market_item_snapshot(self, item: dict[str, Any]) -> MarketSnapshot | None:
        goods_id = item.get("id") or item.get("goods_id")
        if not goods_id:
            return None
        info = item.get("goods_info") or item
        market_hash_name = (
            info.get("market_hash_name")
            or item.get("market_hash_name")
            or info.get("name")
            or item.get("name")
            or ""
        )
        if not market_hash_name:
            return None
        family, condition = split_market_name(market_hash_name)
        price = try_float(item.get("sell_min_price") or item.get("quick_price") or item.get("sell_reference_price"))
        if price is None:
            return None
        return MarketSnapshot(
            goods_id=str(goods_id),
            family=family,
            skin_name=f"{family} ({condition})" if condition and condition not in family else family,
            condition=condition or "Unknown",
            price=price,
            listings=int(try_float(item.get("sell_num")) or 0),
            buy_orders=int(try_float(item.get("buy_num")) or 0),
            reference_price=try_float(item.get("sell_reference_price") or info.get("steam_price_cny")),
            image_url=normalize_image_url(
                info.get("original_icon_url")
                or info.get("icon_url")
                or item.get("original_icon_url")
                or item.get("icon_url")
            ),
            observed_orders=0,
        )

    def discover_snapshots_from_market(
        self,
        *,
        keyword: str,
        category: str | None = None,
        min_price: float,
        max_pages: int = 20,
    ) -> list[MarketSnapshot]:
        snapshots: dict[str, MarketSnapshot] = {}
        for page_num in range(1, max_pages + 1):
            response = self._get(
                self.GOODS_MARKET_URL,
                params={
                    "game": "csgo",
                    "search": keyword,
                    **({"category": category} if category else {}),
                    "min_price": str(int(min_price)),
                    "page_num": page_num,
                    "page_size": 80,
                    "sort_by": "price.desc",
                    "sort_order": "desc",
                },
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                print(f"Failed market search {keyword}: {exc}")
                break
            payload = response.json()
            if payload.get("code") != "OK":
                print(f"Failed market search {keyword}: BUFF code {payload.get('code')}")
                break

            data = payload.get("data") or {}
            items = data.get("items") or []
            if not items:
                break

            for item in items:
                snapshot = self.market_item_snapshot(item)
                if snapshot and snapshot.price >= min_price:
                    snapshots[snapshot.goods_id] = snapshot

            total_page = int(data.get("total_page") or 0)
            if total_page and page_num >= total_page:
                break
            time.sleep(float(os.getenv("BUFF_MARKET_PAGE_DELAY", "1.5")))

        return sorted(
            snapshots.values(),
            key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
        )

    def discover_full_catalog(
        self,
        *,
        keywords: list[str | tuple[str, str | None]],
        seed_goods_ids: list[str] | None = None,
        max_pages_per_keyword: int = 60,
        match_keywords: list[str] | None = None,
    ) -> list[MarketSnapshot]:
        queue = [str(goods_id) for goods_id in (seed_goods_ids or []) if str(goods_id).strip()]
        for query in keywords:
            keyword, category = query if isinstance(query, tuple) else (query, None)
            queue.extend(self.discover_goods_ids_from_market(keyword=keyword, category=category, max_pages=max_pages_per_keyword))
        queue = sorted(set(queue))

        seen: set[str] = set()
        snapshots: dict[str, MarketSnapshot] = {}
        keyword_lower = tuple(keyword.lower() for keyword in (match_keywords or keywords))

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

    def discover_goods_ids_from_market(
        self,
        *,
        keyword: str,
        category: str | None = None,
        max_pages: int = 20,
        min_price: float | None = None,
    ) -> list[str]:
        goods_ids: set[str] = set()
        for page_num in range(1, max_pages + 1):
            response = self._get(
                self.GOODS_MARKET_URL,
                params={
                    "game": "csgo",
                    "search": keyword,
                    "use_suggestion": "0",
                    **({"category": category} if category else {}),
                    "page_num": page_num,
                    "page_size": 80,
                    "sort_by": "price.desc",
                    "sort_order": "desc",
                },
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                print(f"Failed market search {keyword}: {exc}")
                break
            payload = response.json()
            if payload.get("code") != "OK":
                break
            data = payload.get("data") or {}
            items = data.get("items") or []
            if not items:
                break

            for item in items:
                item_price = try_float(
                    item.get("sell_min_price")
                    or item.get("quick_price")
                    or item.get("sell_reference_price")
                    or item.get("steam_price_cny")
                )
                if min_price is not None and item_price is not None and item_price < min_price:
                    continue
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
    goods_cols = {row[1] for row in conn.execute("PRAGMA table_info(goods);")}
    if "reference_price" not in goods_cols:
        conn.execute("ALTER TABLE goods ADD COLUMN reference_price REAL;")
    if "image_url" not in goods_cols:
        conn.execute("ALTER TABLE goods ADD COLUMN image_url TEXT;")

    snapshots_cols = {row[1] for row in conn.execute("PRAGMA table_info(snapshots);")}
    if "buy_orders" not in snapshots_cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN buy_orders INTEGER NOT NULL DEFAULT 0;")
    if "observed_orders" not in snapshots_cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN observed_orders INTEGER NOT NULL DEFAULT 0;")


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
        sqlite_init(conn)
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

    # Local fallback for development only. Production should use secret JSON
    # env vars such as GSHEET_CREDS_JSON, not committed credential files.
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
            # GitHub Actions and most hosts work best with the whole service
            # account JSON stored as one secret environment variable.
            return credentials_from_info(json.loads(raw_json), scope)

    try:
        import streamlit as st

        # Streamlit Cloud stores secrets separately from normal environment
        # variables, so the dashboard supports both deployment styles.
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
    if raw is not None:
        return [item.strip() for item in raw.split(",") if item.strip()]
    legacy_raw = os.getenv("BUFF_BUTTERFLY_SEEDS")
    if legacy_raw:
        return [item.strip() for item in legacy_raw.split(",") if item.strip()]
    return []


def get_track_keywords() -> list[str]:
    raw = os.getenv("BUFF_TRACK_KEYWORDS", ",".join(DEFAULT_TRACK_KEYWORDS))
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_search_keywords(track_keywords: list[str]) -> list[str | tuple[str, str | None]]:
    raw = os.getenv("BUFF_SEARCH_KEYWORDS")
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    expand_finishes = env_flag("BUFF_EXPAND_FINISH_SEARCHES", False)
    searches: list[str | tuple[str, str | None]] = []
    for knife in track_keywords:
        category = DEFAULT_KNIFE_CATEGORIES.get(knife)
        searches.append((knife, category))
        if expand_finishes:
            searches.extend((finish, category) for finish in DEFAULT_KNIFE_FINISHES)
    return searches


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
        snapshots.append(
            MarketSnapshot(
                goods_id=source_id("csgotrader", market_hash_name),
                family=family,
                skin_name=f"{family} ({condition})" if condition and condition not in family else family,
                condition=condition or "Unknown",
                price=price,
                listings=0,
                buy_orders=0,
                reference_price=try_float((highest_order or {}).get("price")) * usd_to_cny
                if try_float((highest_order or {}).get("price")) is not None
                else None,
                image_url=image_url,
                observed_orders=0,
            )
        )
    if fill_images:
        save_json_file(STEAM_IMAGE_CACHE_PATH, image_cache)
    return sorted(snapshots, key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id))


def merge_direct_and_fallback_snapshots(
    direct_snapshots: list[MarketSnapshot],
    fallback_snapshots: list[MarketSnapshot],
) -> list[MarketSnapshot]:
    """Merge direct BUFF rows with broad fallback price coverage.

    Direct BUFF rows are preferred because they include live listings and buy
    orders. Fallback rows fill price gaps for knives that the direct scan did
    not find during that scheduled run.
    """
    snapshots_by_market_key = {
        (snapshot.family, snapshot.condition): snapshot
        for snapshot in direct_snapshots
    }
    for snapshot in fallback_snapshots:
        # Fallback fills missing price rows only. Direct BUFF snapshots keep
        # richer live listing/buy-order data when both sources find a skin.
        snapshots_by_market_key.setdefault((snapshot.family, snapshot.condition), snapshot)
    return sorted(
        snapshots_by_market_key.values(),
        key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
    )


def enrich_fallback_snapshots_with_latest_depth(
    snapshots: list[MarketSnapshot],
    history: pd.DataFrame,
) -> tuple[list[MarketSnapshot], int]:
    """Backfill fallback listing/buy-order depth from latest known history.

    CSGOTrader fallback rows improve price coverage but do not provide live
    BUFF listing depth. For fallback-only rows, we reuse the latest known
    listing/buy-order values for the same market key (family + condition).
    """
    if not snapshots or history.empty:
        return snapshots, 0

    required_cols = {"Timestamp", "Family", "Condition", "Listings"}
    if not required_cols.issubset(set(history.columns)):
        return snapshots, 0

    frame = history.copy()
    frame["Timestamp"] = pd.to_datetime(frame["Timestamp"], errors="coerce", utc=True)
    frame["Family"] = frame["Family"].fillna("").astype(str).map(canonicalize_family_name)
    frame["Condition"] = frame["Condition"].fillna("Unknown").astype(str)
    frame["Listings"] = pd.to_numeric(frame["Listings"], errors="coerce")
    frame["Buy Orders"] = pd.to_numeric(frame.get("Buy Orders"), errors="coerce").fillna(0)
    frame = frame.dropna(subset=["Timestamp", "Family", "Condition", "Listings"]).sort_values("Timestamp")
    if frame.empty:
        return snapshots, 0

    latest_by_key: dict[tuple[str, str], tuple[int, int]] = {}
    for row in frame[["Family", "Condition", "Listings", "Buy Orders"]].itertuples(index=False):
        listings = max(0, int(round(float(row[2]))))
        buy_orders = max(0, int(round(float(row[3]))))
        if listings <= 0 and buy_orders <= 0:
            continue
        latest_by_key[(row[0], row[1])] = (listings, buy_orders)
    if not latest_by_key:
        return snapshots, 0

    enriched_snapshots: list[MarketSnapshot] = []
    filled_rows = 0
    for snapshot in snapshots:
        if not snapshot.goods_id.startswith("csgotrader:"):
            enriched_snapshots.append(snapshot)
            continue
        needs_listings = snapshot.listings <= 0
        needs_buy_orders = snapshot.buy_orders <= 0
        if not (needs_listings or needs_buy_orders):
            enriched_snapshots.append(snapshot)
            continue

        key = (canonicalize_family_name(snapshot.family), snapshot.condition)
        depth = latest_by_key.get(key)
        if depth is None:
            enriched_snapshots.append(snapshot)
            continue

        listings, buy_orders = depth
        updated = MarketSnapshot(
            goods_id=snapshot.goods_id,
            family=snapshot.family,
            skin_name=snapshot.skin_name,
            condition=snapshot.condition,
            price=snapshot.price,
            listings=listings if needs_listings else snapshot.listings,
            buy_orders=buy_orders if needs_buy_orders else snapshot.buy_orders,
            reference_price=snapshot.reference_price,
            image_url=snapshot.image_url,
            observed_orders=snapshot.observed_orders,
        )
        if updated.listings != snapshot.listings or updated.buy_orders != snapshot.buy_orders:
            filled_rows += 1
        enriched_snapshots.append(updated)
    return enriched_snapshots, filled_rows


def run(migrate_only: bool = False) -> None:
    sqlite_path = os.getenv("BUFF_SQLITE_PATH", DEFAULT_SQLITE_PATH).strip()
    enable_sqlite = env_flag("BUFF_WRITE_SQLITE", False)
    write_sheets = env_flag("BUFF_WRITE_SHEETS", not enable_sqlite)
    store = SheetStore(SHEET_NAME) if write_sheets or migrate_only or env_flag("BUFF_RUN_MIGRATION", False) else None
    run_migration = migrate_only or env_flag("BUFF_RUN_MIGRATION", False)
    if run_migration:
        if store is None:
            raise ValueError("Sheet migration requires Google Sheets.")
        migrated_rows = migrate_history_sheet(store)
        if migrated_rows:
            print(f"Migrated {migrated_rows} history rows to the current schema.")
    else:
        print("Skipping migration for this run (BUFF_RUN_MIGRATION is disabled).")

    history = load_history_frame(store) if store is not None else sqlite_load_history_frame(sqlite_path)
    if migrate_only:
        agent = PriceAnalysisAgent(history)
        tracked_names = sorted(history["Skin Name"].dropna().unique().tolist())
        analysis_rows = [summary for name in tracked_names if (summary := agent.summarize_skin(name))]
        if store is None:
            raise ValueError("Migration-only run requires Google Sheets.")
        rebuild_dashboard(store, analysis_rows)
        rebuild_signals(store, analysis_rows, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        if env_flag("BUFF_ENABLE_FORECAST", True):
            rebuild_forecast(store, history)
        print("Migration-only run completed.")
        return

    client = BuffPriceClient()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    min_price = float(os.getenv("BUFF_MIN_PRICE_CNY", "0"))
    try:
        high_value_pages = max(1, int(os.getenv("BUFF_HIGH_VALUE_PAGES", "25")))
    except ValueError:
        high_value_pages = 25
    track_keywords = get_track_keywords()
    search_keywords = get_search_keywords(track_keywords)
    snapshots: list[MarketSnapshot] = []
    if not env_flag("BUFF_SKIP_DIRECT", False):
        max_goods_raw = os.getenv("BUFF_MAX_GOODS_PER_RUN", "").strip()
        max_goods = int(max_goods_raw) if max_goods_raw else None
        snapshots = client.discover_high_value_catalog(
            keywords=search_keywords,
            min_price=min_price,
            seed_goods_ids=get_seed_goods_ids(),
            max_pages_per_keyword=high_value_pages,
            match_keywords=track_keywords,
            max_goods=max_goods,
            on_snapshot=(
                (lambda snapshot: sqlite_write_snapshots(sqlite_path, [snapshot], timestamp))
                if enable_sqlite and sqlite_path and not write_sheets
                else None
            ),
        )
    if env_flag("BUFF_FALLBACK_CSGOTRADER", False):
        fallback_snapshots = csgotrader_snapshots(track_keywords, min_price)
        fallback_snapshots, backfilled_rows = enrich_fallback_snapshots_with_latest_depth(fallback_snapshots, history)
        if backfilled_rows:
            print(f"Fallback depth backfill: {backfilled_rows} rows reused latest listing depth.")
        min_fallback_snapshots = int(os.getenv("BUFF_MIN_FALLBACK_SNAPSHOTS", "0") or "0")
        if min_fallback_snapshots and len(fallback_snapshots) < min_fallback_snapshots:
            # A tiny fallback result would silently create missing price days.
            # Failing the workflow is safer because GitHub Actions will show it.
            raise RuntimeError(
                "Fallback source returned too few tracked snapshots: "
                f"{len(fallback_snapshots)} < {min_fallback_snapshots}."
            )
        direct_count = len(snapshots)
        snapshots = merge_direct_and_fallback_snapshots(snapshots, fallback_snapshots)
        print(
            f"Fallback merge: direct={direct_count}, "
            f"fallback={len(fallback_snapshots)}, final={len(snapshots)}."
        )
        if enable_sqlite and sqlite_path and not write_sheets:
            sqlite_write_snapshots(sqlite_path, fallback_snapshots, timestamp)

    full_catalog_enabled = os.getenv("BUFF_FULL_CATALOG", "").strip().lower() in {"1", "true", "yes", "on"}
    if full_catalog_enabled:
        max_pages = int(os.getenv("BUFF_FULL_CATALOG_PAGES", "60"))
        full_snapshots = client.discover_full_catalog(
            keywords=search_keywords,
            seed_goods_ids=get_seed_goods_ids(),
            max_pages_per_keyword=max_pages,
            match_keywords=track_keywords,
        )
        rebuild_all_catalog(store, full_snapshots, timestamp)

    if enable_sqlite and sqlite_path and write_sheets:
        sqlite_write_snapshots(sqlite_path, snapshots, timestamp)

    if not write_sheets:
        print(
            f"Collected {len(snapshots)} high-value snapshots for {', '.join(track_keywords)} "
            f"(>= {min_price:.0f} CNY, pages={high_value_pages})."
        )
        return

    if store is None:
        raise ValueError("Google Sheets output is enabled but no sheet store is configured.")
    rebuild_catalog(store, snapshots)
    append_history(store, snapshots, timestamp)

    history = load_history_frame(store)
    agent = PriceAnalysisAgent(history)
    tracked_names = sorted(set(history["Skin Name"].dropna().unique().tolist()))
    analysis_rows = [summary for name in tracked_names if (summary := agent.summarize_skin(name))]

    rebuild_dashboard(store, analysis_rows)
    rebuild_signals(store, analysis_rows, timestamp)
    if env_flag("BUFF_ENABLE_FORECAST", False):
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
