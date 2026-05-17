from __future__ import annotations

import asyncio

from src.client import AsyncBuffPriceClient


class _Resp:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_fetch_many_returns_snapshots(mock_buff_response):
    client = AsyncBuffPriceClient(timeout=5)

    class _MockAsync:
        async def get(self, *args, **kwargs):
            gid = kwargs["params"]["goods_id"]
            return _Resp(mock_buff_response(str(gid), 100.0, 5))

        async def aclose(self):
            return None

    client._client = _MockAsync()
    out = asyncio.run(client.fetch_many(["1", "2", "3"], concurrency=2))
    assert len(out) == 3
