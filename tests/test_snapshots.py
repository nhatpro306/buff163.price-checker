from __future__ import annotations

from src.snapshots import build_market_item_snapshot, build_sell_order_snapshot


def test_build_sell_order_snapshot_uses_page_meta(mock_buff_response):
    payload = mock_buff_response("1", 123.4, 11)
    data = payload["data"]
    info = data["goods_infos"]["1"]

    snapshot = build_sell_order_snapshot(
        goods_id="1",
        data=data,
        info=info,
        items=data["items"],
        page_meta={"sell_num": 99, "buy_num": 7, "image_url": "//example/image.png"},
    )

    assert snapshot.price == 123.4
    assert snapshot.listings == 99
    assert snapshot.buy_orders == 7
    assert snapshot.image_url.startswith("https://")


def test_build_market_item_snapshot_success():
    snapshot = build_market_item_snapshot(
        {
            "id": "42",
            "market_hash_name": "Karambit | Doppler (Factory New)",
            "sell_min_price": "100.5",
            "sell_num": "3",
            "buy_num": "2",
        }
    )

    assert snapshot is not None
    assert snapshot.goods_id == "42"
    assert snapshot.condition == "Factory New"
    assert snapshot.price == 100.5
    assert snapshot.listings == 3
    assert snapshot.buy_orders == 2


def test_build_market_item_snapshot_uses_nested_listing_aliases():
    snapshot = build_market_item_snapshot(
        {
            "id": "755862",
            "sell_min_price": "1639.08",
            "goods_info": {
                "market_hash_name": "Bayonet (Unknown)",
                "sell_order_count": "1,234",
                "buy_order_count": "17",
            },
        }
    )

    assert snapshot is not None
    assert snapshot.goods_id == "755862"
    assert snapshot.listings == 1234
    assert snapshot.buy_orders == 17


def test_build_market_item_snapshot_missing_price():
    assert (
        build_market_item_snapshot(
            {"id": "42", "market_hash_name": "Karambit | Doppler (Factory New)"}
        )
        is None
    )
