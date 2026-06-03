from __future__ import annotations

from market_models import MarketSnapshot
from src.validation import is_valid_snapshot, validate_snapshot


def _snap(
    *,
    goods_id: str = "42552",
    skin_name: str = "Karambit | Doppler (Factory New)",
    price: float = 1000.0,
    listings: int = 10,
) -> MarketSnapshot:
    return MarketSnapshot(
        goods_id=goods_id,
        family="Karambit",
        skin_name=skin_name,
        condition="Factory New",
        price=price,
        listings=listings,
        buy_orders=5,
        reference_price=1010.0,
        image_url="https://example.com/img.png",
        observed_orders=10,
    )


def test_valid_snapshot_has_no_errors():
    assert validate_snapshot(_snap()) == []
    assert is_valid_snapshot(_snap())


def test_empty_goods_id_rejected():
    assert "empty goods_id" in validate_snapshot(_snap(goods_id="  "))


def test_zero_price_rejected():
    assert any("price" in e for e in validate_snapshot(_snap(price=0.0)))


def test_negative_price_rejected():
    assert any("price" in e for e in validate_snapshot(_snap(price=-5.0)))


def test_negative_listings_rejected():
    assert any("listings" in e for e in validate_snapshot(_snap(listings=-1)))


def test_zero_listings_allowed():
    assert is_valid_snapshot(_snap(listings=0))


def test_empty_skin_name_rejected():
    assert any("skin_name" in e for e in validate_snapshot(_snap(skin_name="   ")))
