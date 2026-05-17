from __future__ import annotations

import asyncio
import json
import os
import re
import time
from http.cookies import SimpleCookie
from typing import Any

import httpx
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from market_config import CONDITION_ORDER
from market_models import MarketSnapshot
from market_utils import clean_html_text, normalize_image_url, split_market_name, try_float


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

    def fetch_sell_snapshot(
        self, goods_id: str, page_meta: dict[str, Any] | None = None
    ) -> MarketSnapshot:
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
            skin_name=(
                f"{family} ({condition})" if condition and condition not in family else family
            ),
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

        goods_info_match = re.search(
            r"var goods_info = (\{.*?\})\s*market_show\.pre_init", page, re.DOTALL
        )
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

        return sorted(
            snapshots.values(), key=lambda item: (item.family, item.condition, item.goods_id)
        )

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
        raw_keywords = match_keywords or [
            value if isinstance(value, str) else value[0] for value in keywords
        ]
        keyword_lower = tuple(keyword.lower() for keyword in raw_keywords)

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
            if snapshot.price >= min_price and any(
                keyword in family_lower for keyword in keyword_lower
            ):
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
        price = try_float(
            item.get("sell_min_price")
            or item.get("quick_price")
            or item.get("sell_reference_price")
        )
        if price is None:
            return None
        return MarketSnapshot(
            goods_id=str(goods_id),
            family=family,
            skin_name=(
                f"{family} ({condition})" if condition and condition not in family else family
            ),
            condition=condition or "Unknown",
            price=price,
            listings=int(try_float(item.get("sell_num")) or 0),
            buy_orders=int(try_float(item.get("buy_num")) or 0),
            reference_price=try_float(
                item.get("sell_reference_price") or info.get("steam_price_cny")
            ),
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
            queue.extend(
                self.discover_goods_ids_from_market(
                    keyword=keyword, category=category, max_pages=max_pages_per_keyword
                )
            )
        queue = sorted(set(queue))

        seen: set[str] = set()
        snapshots: dict[str, MarketSnapshot] = {}
        raw_keywords = match_keywords or [
            value if isinstance(value, str) else value[0] for value in keywords
        ]
        keyword_lower = tuple(keyword.lower() for keyword in raw_keywords)

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


class AsyncBuffPriceClient:
    SELL_ORDER_URL = BuffPriceClient.SELL_ORDER_URL

    def __init__(self, timeout: int | None = None) -> None:
        if timeout is None:
            timeout = int(os.getenv("BUFF_REQUEST_TIMEOUT", "20"))
        self.timeout = timeout
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://buff.163.com/market/csgo",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        cookie = os.getenv("BUFF_COOKIE")
        if cookie:
            headers["Cookie"] = cookie
            parsed_cookie = SimpleCookie()
            try:
                parsed_cookie.load(cookie)
                csrf_token = parsed_cookie.get("csrf_token")
            except Exception:
                csrf_token = None
            if csrf_token:
                headers["X-CSRFToken"] = csrf_token.value

        self._client = httpx.AsyncClient(timeout=self.timeout, headers=headers)

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        max_attempts = max(1, int(os.getenv("BUFF_MAX_429_ATTEMPTS", "5")))
        response: httpx.Response | None = None
        for attempt in range(max_attempts):
            response = await self._client.get(url, **kwargs)
            if response.status_code != 429:
                return response
            backoff_seconds = min(2.0 + attempt * 1.5, 8.0)
            await asyncio.sleep(backoff_seconds)
        if response is None:
            raise RuntimeError("No response from async client")
        return response

    async def fetch_sell_snapshot(
        self, goods_id: str, page_meta: dict[str, Any] | None = None
    ) -> MarketSnapshot:
        response = await self._get(
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

        market_hash_name = info.get("market_hash_name") or info.get("name") or f"Goods {goods_id}"
        family, condition = split_market_name(market_hash_name)

        return MarketSnapshot(
            goods_id=str(goods_id),
            family=family,
            skin_name=(
                f"{family} ({condition})" if condition and condition not in family else family
            ),
            condition=condition or "Unknown",
            price=float(items[0]["price"]),
            listings=int(
                (page_meta or {}).get("sell_num") or data.get("total_count") or len(items)
            ),
            buy_orders=int((page_meta or {}).get("buy_num") or 0),
            reference_price=try_float(info.get("steam_price_cny")),
            image_url=normalize_image_url(
                info.get("original_icon_url")
                or info.get("icon_url")
                or (page_meta or {}).get("original_icon_url")
                or (page_meta or {}).get("icon_url")
                or (page_meta or {}).get("image_url")
            ),
            observed_orders=len(items),
        )

    async def fetch_many(self, goods_ids: list[str], concurrency: int = 5) -> list[MarketSnapshot]:
        sem = asyncio.Semaphore(max(1, concurrency))
        snapshots: list[MarketSnapshot] = []

        async def _task(goods_id: str) -> None:
            async with sem:
                snapshot = await self.fetch_sell_snapshot(goods_id)
                snapshots.append(snapshot)

        await asyncio.gather(*[_task(str(gid)) for gid in goods_ids])
        return snapshots

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = ["BuffPriceClient", "AsyncBuffPriceClient"]
