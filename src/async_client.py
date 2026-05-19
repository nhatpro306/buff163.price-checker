from __future__ import annotations

import asyncio
from typing import Any

import httpx

from market_models import MarketSnapshot
from market_utils import debug_log
from src.buff_http import buff_headers, max_429_attempts, request_timeout
from src.snapshots import build_sell_order_snapshot


class AsyncBuffPriceClient:
    SELL_ORDER_URL = "https://buff.163.com/api/market/goods/sell_order"

    def __init__(self, timeout: int | None = None) -> None:
        if timeout is None:
            timeout = request_timeout()
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=self.timeout, headers=buff_headers())

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        max_attempts = max_429_attempts()
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

        return build_sell_order_snapshot(
            goods_id=str(goods_id),
            data=data,
            info=info,
            items=items,
            page_meta=page_meta,
        )

    async def fetch_many(self, goods_ids: list[str], concurrency: int = 5) -> list[MarketSnapshot]:
        sem = asyncio.Semaphore(max(1, concurrency))
        snapshots: list[MarketSnapshot] = []
        failures = 0

        async def _task(goods_id: str) -> None:
            nonlocal failures
            async with sem:
                try:
                    snapshot = await self.fetch_sell_snapshot(goods_id)
                except Exception as exc:
                    failures += 1
                    debug_log(f"async_fetch_many skip goods_id={goods_id} error={exc}")
                    return
                snapshots.append(snapshot)

        await asyncio.gather(*[_task(str(gid)) for gid in goods_ids])
        debug_log(
            "async_fetch_many final "
            f"requested={len(goods_ids)} fetched={len(snapshots)} failures={failures} "
            f"concurrency={concurrency}"
        )
        return snapshots

    async def aclose(self) -> None:
        await self._client.aclose()
