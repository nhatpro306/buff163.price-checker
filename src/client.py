from __future__ import annotations

import time
from typing import Any

import requests

from market_models import MarketSnapshot
from src.async_client import AsyncBuffPriceClient
from src.buff_http import buff_headers, request_timeout
from src.page_parser import parse_goods_page_metadata
from src.retry import (
    backoff_base_seconds,
    compute_backoff,
    is_retryable_status,
)
from src.retry import max_retries as _max_retries
from src.snapshots import build_market_item_snapshot, build_sell_order_snapshot


class BuffPriceClient:
    SELL_ORDER_URL = "https://buff.163.com/api/market/goods/sell_order"
    GOODS_MARKET_URL = "https://buff.163.com/api/market/goods"
    GOODS_PAGE_URL = "https://buff.163.com/goods/{goods_id}?from=market#tab=selling"

    def __init__(
        self,
        timeout: int | None = None,
        *,
        max_retries: int | None = None,
        backoff_base: float | None = None,
    ) -> None:
        if timeout is None:
            timeout = request_timeout()
        self.timeout = timeout
        # Retry budget = extra attempts after the first try. Transient HTTP
        # failures and network errors are retried here (with backoff + jitter)
        # so a temporary BUFF hiccup does not fail a scheduled run.
        self.max_retries = max_retries if max_retries is not None else _max_retries()
        self.backoff_base = backoff_base if backoff_base is not None else backoff_base_seconds()
        self.session = requests.Session()
        self.page_cache: dict[str, dict[str, Any]] = {}
        self.session.headers.update(buff_headers())

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        # attempt 0 = first try; attempts 1..max_retries = retries.
        last_exc: Exception | None = None
        response: requests.Response | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout, **kwargs)
            except (requests.Timeout, requests.ConnectionError) as exc:
                # Transient network failure: retry unless budget exhausted.
                last_exc = exc
                if attempt >= self.max_retries:
                    raise
                time.sleep(compute_backoff(attempt, self.backoff_base))
                continue
            # 4xx (e.g. 403/404) returned as-is so callers raise_for_status;
            # only transient statuses are retried.
            if is_retryable_status(response.status_code) and attempt < self.max_retries:
                time.sleep(compute_backoff(attempt, self.backoff_base))
                continue
            return response
        if response is not None:
            return response
        assert last_exc is not None
        raise last_exc

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
