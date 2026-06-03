from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

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
    with (
        patch.object(client, "_get", return_value=_Resp(200, mock_buff_response("1", 123.4, 11))),
        patch.object(
            client, "fetch_goods_page_metadata", return_value={"sell_num": 11, "buy_num": 5}
        ),
    ):
        snap = client.fetch_sell_snapshot("1")
    assert snap.price == 123.4
    assert snap.listings == 11
    assert "Karambit" in snap.family


def test_fetch_sell_snapshot_bad_code():
    client = BuffPriceClient(timeout=5)
    with patch.object(
        client, "_get", return_value=_Resp(200, {"code": "Login Required", "data": {}})
    ):
        with pytest.raises(ValueError):
            client.fetch_sell_snapshot("1")


def test_retry_on_429(mock_buff_response):
    client = BuffPriceClient(timeout=5)
    responses = [_Resp(429, {}), _Resp(429, {}), _Resp(200, mock_buff_response("1", 10.0, 2))]
    with (
        patch("main.time.sleep") as sleep_mock,
        patch.object(client.session, "get", MagicMock(side_effect=responses)),
    ):
        res = client._get("https://example.com")
        assert res.status_code == 200
        assert sleep_mock.call_count == 2


def test_market_item_snapshot_missing_price():
    client = BuffPriceClient(timeout=5)
    out = client.market_item_snapshot(
        {"id": "1", "market_hash_name": "Karambit | Doppler (Factory New)"}
    )
    assert out is None


# --- _get retry behaviour -------------------------------------------------


def _client(max_retries=3):
    return BuffPriceClient(timeout=5, max_retries=max_retries, backoff_base=0.01)


def test_get_timeout_then_success():
    client = _client(max_retries=3)
    ok = _Resp(200, {"code": "OK"})
    with (
        patch.object(client.session, "get", MagicMock(side_effect=[requests.Timeout(), ok])),
        patch("src.client.time.sleep") as sleep_mock,
    ):
        res = client._get("https://example.com")
    assert res is ok
    assert sleep_mock.call_count == 1


def test_get_timeout_exhausted_raises():
    client = _client(max_retries=1)
    with (
        patch.object(
            client.session, "get", MagicMock(side_effect=[requests.Timeout(), requests.Timeout()])
        ),
        patch("src.client.time.sleep") as sleep_mock,
    ):
        with pytest.raises(requests.Timeout):
            client._get("https://example.com")
    assert sleep_mock.call_count == 1


def test_get_connection_error_exhausted_raises():
    client = _client(max_retries=2)
    get_mock = MagicMock(side_effect=requests.ConnectionError())
    with (
        patch.object(client.session, "get", get_mock),
        patch("src.client.time.sleep") as sleep_mock,
    ):
        with pytest.raises(requests.ConnectionError):
            client._get("https://example.com")
    # 1 first try + 2 retries = 3 calls, 2 sleeps.
    assert get_mock.call_count == 3
    assert sleep_mock.call_count == 2


def test_get_500_then_success():
    client = _client(max_retries=3)
    ok = _Resp(200, {"code": "OK"})
    with (
        patch.object(client.session, "get", MagicMock(side_effect=[_Resp(500), ok])),
        patch("src.client.time.sleep") as sleep_mock,
    ):
        res = client._get("https://example.com")
    assert res is ok
    assert sleep_mock.call_count == 1


def test_get_500_exhausted_returns_last_response():
    client = _client(max_retries=1)
    with (
        patch.object(client.session, "get", MagicMock(side_effect=[_Resp(500), _Resp(500)])),
        patch("src.client.time.sleep") as sleep_mock,
    ):
        res = client._get("https://example.com")
    assert res.status_code == 500
    assert sleep_mock.call_count == 1


def test_get_403_not_retried():
    client = _client(max_retries=3)
    get_mock = MagicMock(return_value=_Resp(403))
    with (
        patch.object(client.session, "get", get_mock),
        patch("src.client.time.sleep") as sleep_mock,
    ):
        res = client._get("https://example.com")
    assert res.status_code == 403
    assert get_mock.call_count == 1
    assert sleep_mock.call_count == 0


def test_get_404_not_retried():
    client = _client(max_retries=3)
    get_mock = MagicMock(return_value=_Resp(404))
    with (
        patch.object(client.session, "get", get_mock),
        patch("src.client.time.sleep") as sleep_mock,
    ):
        res = client._get("https://example.com")
    assert res.status_code == 404
    assert get_mock.call_count == 1
    assert sleep_mock.call_count == 0
