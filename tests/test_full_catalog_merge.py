import unittest

from main import merge_snapshots_with_full_catalog
from market_models import MarketSnapshot


def snapshot(
    goods_id: str,
    family: str,
    condition: str,
    price: float,
    listings: int,
    buy_orders: int,
) -> MarketSnapshot:
    return MarketSnapshot(
        goods_id=goods_id,
        family=family,
        skin_name=f"{family} ({condition})",
        condition=condition,
        price=price,
        listings=listings,
        buy_orders=buy_orders,
        reference_price=None,
        image_url="",
        observed_orders=0,
    )


class FullCatalogMergeTests(unittest.TestCase):
    def test_enriches_same_key_listings_from_full_catalog(self) -> None:
        primary = [snapshot("csgotrader:1", "Butterfly Knife | Fade", "Factory New", 1000, 0, 0)]
        full = [snapshot("123", "Butterfly Knife | Fade", "Factory New", 1005, 22, 8)]

        merged = merge_snapshots_with_full_catalog(primary, full)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].price, 1000)  # keep primary price source
        self.assertEqual(merged[0].listings, 22)
        self.assertEqual(merged[0].buy_orders, 8)

    def test_adds_missing_keys_from_full_catalog(self) -> None:
        primary = [snapshot("111", "Butterfly Knife | Fade", "Factory New", 1000, 5, 2)]
        full = [snapshot("222", "Karambit | Doppler", "Minimal Wear", 900, 11, 4)]

        merged = merge_snapshots_with_full_catalog(primary, full)

        self.assertEqual(len(merged), 2)
        families = {item.family for item in merged}
        self.assertEqual(families, {"Butterfly Knife | Fade", "Karambit | Doppler"})


if __name__ == "__main__":
    unittest.main()
