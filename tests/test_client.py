from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from main import BuffPriceClient


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code != 429:
            raise Exception("http error")

    def json(self):
        return self._payload


def test_fetch_sell_snapshot_success(mock_buff_response):
    client = BuffPriceClient(timeout=5)
    client._get = MagicMock(return_value=_Resp(200, mock_buff_response("1", 123.4, 11)))
    client.fetch_goods_page_metadata = MagicMock(return_value={"sell_num": 11, "buy_num": 5})
    snap = client.fetch_sell_snapshot("1")
    assert snap.price == 123.4
    assert snap.listings == 11
    assert "Karambit" in snap.family


def test_fetch_sell_snapshot_bad_code():
    client = BuffPriceClient(timeout=5)
    client._get = MagicMock(return_value=_Resp(200, {"code": "Login Required", "data": {}}))
    with pytest.raises(ValueError):
        client.fetch_sell_snapshot("1")


def test_retry_on_429(mock_buff_response):
    client = BuffPriceClient(timeout=5)
    responses = [_Resp(429, {}), _Resp(429, {}), _Resp(200, mock_buff_response("1", 10.0, 2))]
    with patch("main.time.sleep") as sleep_mock:
        client.session.get = MagicMock(side_effect=responses)
        res = client._get("https://example.com")
        assert res.status_code == 200
        assert sleep_mock.call_count == 2


def test_market_item_snapshot_missing_price():
    client = BuffPriceClient(timeout=5)
    out = client.market_item_snapshot(
        {"id": "1", "market_hash_name": "Karambit | Doppler (Factory New)"}
    )
    assert out is None
