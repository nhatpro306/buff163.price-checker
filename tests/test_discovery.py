from __future__ import annotations

from src.discovery import discover_goods_ids_from_market, discover_snapshots_from_market
from src.snapshots import build_market_item_snapshot


class _Response:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Client:
    GOODS_MARKET_URL = "https://example.test/market"

    def __init__(self, payload: dict):
        self.payload = payload

    def _get(self, _url: str, **_kwargs):
        return _Response(self.payload)

    def market_item_snapshot(self, item: dict):
        return build_market_item_snapshot(item)


def test_discover_goods_ids_from_market_filters_by_min_price():
    client = _Client(
        {
            "code": "OK",
            "data": {
                "items": [
                    {"id": "1", "sell_min_price": "90"},
                    {"id": "2", "sell_min_price": "150"},
                ],
                "total_page": 1,
            },
        }
    )

    assert discover_goods_ids_from_market(client, keyword="Karambit", min_price=100) == ["2"]


def test_discover_snapshots_from_market_builds_sorted_snapshots():
    client = _Client(
        {
            "code": "OK",
            "data": {
                "items": [
                    {
                        "id": "2",
                        "market_hash_name": "Karambit | Doppler (Factory New)",
                        "sell_min_price": "150",
                        "goods_info": {"sell_order_count": "8", "buy_order_count": "3"},
                    },
                    {
                        "id": "1",
                        "market_hash_name": "Butterfly Knife | Fade (Factory New)",
                        "sell_min_price": "200",
                        "sell_count": "12",
                        "buy_count": "4",
                    },
                ],
                "total_page": 1,
            },
        }
    )

    snapshots = discover_snapshots_from_market(client, keyword="Knife", min_price=100)

    assert [snapshot.goods_id for snapshot in snapshots] == ["1", "2"]
    assert all(snapshot.price >= 100 for snapshot in snapshots)
    assert {snapshot.goods_id: snapshot.listings for snapshot in snapshots} == {"1": 12, "2": 8}
    assert {snapshot.goods_id: snapshot.buy_orders for snapshot in snapshots} == {"1": 4, "2": 3}
