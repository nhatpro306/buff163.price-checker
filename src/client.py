from __future__ import annotations

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from market_models import MarketSnapshot
from src.async_client import AsyncBuffPriceClient
from src.buff_http import buff_headers, max_429_attempts, request_timeout
from src.page_parser import parse_goods_page_metadata
from src.snapshots import build_market_item_snapshot, build_sell_order_snapshot


class BuffPriceClient:
    SELL_ORDER_URL = "https://buff.163.com/api/market/goods/sell_order"
    GOODS_MARKET_URL = "https://buff.163.com/api/market/goods"
    GOODS_PAGE_URL = "https://buff.163.com/goods/{goods_id}?from=market#tab=selling"

    def __init__(self, timeout: int | None = None) -> None:
        if timeout is None:
            timeout = request_timeout()
        self.timeout = timeout
        self.session = requests.Session()
        self.page_cache: dict[str, dict[str, Any]] = {}
        # Retry safe GET requests so temporary BUFF failures do not fail scheduled runs.
        retry = Retry(
            total=2,
            backoff_factor=0.7,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(buff_headers())

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        max_attempts = max_429_attempts()
        for attempt in range(max_attempts):
            response = self.session.get(url, timeout=self.timeout, **kwargs)
            if response.status_code != 429:
                return response
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
        return build_sell_order_snapshot(
            goods_id=str(goods_id),
            data=data,
            info=info,
            items=items,
            page_meta=page_meta,
        )

    def fetch_goods_page_metadata(self, goods_id: str) -> dict[str, Any]:
        goods_id = str(goods_id)
        if goods_id in self.page_cache:
            return self.page_cache[goods_id]

        response = self._get(self.GOODS_PAGE_URL.format(goods_id=goods_id))
        response.raise_for_status()
        page_info = parse_goods_page_metadata(response.text, goods_id)
        self.page_cache[goods_id] = page_info
        return page_info

    def discover_butterfly_catalog(self, seed_goods_ids: list[str]) -> list[MarketSnapshot]:
        from src.discovery import discover_butterfly_catalog

        return discover_butterfly_catalog(self, seed_goods_ids)

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
        from src.discovery import discover_high_value_catalog

        return discover_high_value_catalog(
            self,
            keywords=keywords,
            min_price=min_price,
            seed_goods_ids=seed_goods_ids,
            max_pages_per_keyword=max_pages_per_keyword,
            match_keywords=match_keywords,
            on_snapshot=on_snapshot,
            max_goods=max_goods,
        )

    def market_item_snapshot(self, item: dict[str, Any]) -> MarketSnapshot | None:
        return build_market_item_snapshot(item)

    def discover_snapshots_from_market(
        self,
        *,
        keyword: str,
        category: str | None = None,
        min_price: float,
        max_pages: int = 20,
    ) -> list[MarketSnapshot]:
        from src.discovery import discover_snapshots_from_market

        return discover_snapshots_from_market(
            self,
            keyword=keyword,
            category=category,
            min_price=min_price,
            max_pages=max_pages,
        )

    def discover_full_catalog(
        self,
        *,
        keywords: list[str | tuple[str, str | None]],
        seed_goods_ids: list[str] | None = None,
        max_pages_per_keyword: int = 60,
        match_keywords: list[str] | None = None,
    ) -> list[MarketSnapshot]:
        from src.discovery import discover_full_catalog

        return discover_full_catalog(
            self,
            keywords=keywords,
            seed_goods_ids=seed_goods_ids,
            max_pages_per_keyword=max_pages_per_keyword,
            match_keywords=match_keywords,
        )

    def discover_goods_ids_from_market(
        self,
        *,
        keyword: str,
        category: str | None = None,
        max_pages: int = 20,
        min_price: float | None = None,
    ) -> list[str]:
        from src.discovery import discover_goods_ids_from_market

        return discover_goods_ids_from_market(
            self,
            keyword=keyword,
            category=category,
            max_pages=max_pages,
            min_price=min_price,
        )


__all__ = ["BuffPriceClient", "AsyncBuffPriceClient"]
