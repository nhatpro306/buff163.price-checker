from __future__ import annotations

import asyncio
import os
from http.cookies import SimpleCookie
from typing import Any

import httpx

from main import (
    BuffPriceClient,
    MarketSnapshot,
    csgotrader_snapshots,
    normalize_image_url,
    split_market_name,
    try_float,
)


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


__all__ = ["BuffPriceClient", "AsyncBuffPriceClient", "csgotrader_snapshots"]
