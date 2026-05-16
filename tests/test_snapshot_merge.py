import unittest

from main import MarketSnapshot, merge_direct_and_fallback_snapshots


def snapshot(
    goods_id: str,
    family: str,
    condition: str,
    price: float,
    listings: int,
) -> MarketSnapshot:
    return MarketSnapshot(
        goods_id=goods_id,
        family=family,
        skin_name=f"{family} ({condition})",
        condition=condition,
        price=price,
        listings=listings,
        buy_orders=0,
        reference_price=None,
        image_url="",
        observed_orders=0,
    )


class SnapshotMergeTests(unittest.TestCase):
    def test_direct_snapshot_wins_over_fallback_for_same_market_key(self) -> None:
        direct = snapshot("123", "Butterfly Knife | Fade", "Factory New", 1000, 7)
        fallback = snapshot("csgotrader:fade", "Butterfly Knife | Fade", "Factory New", 999, 0)

        merged = merge_direct_and_fallback_snapshots([direct], [fallback])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].goods_id, "123")
        self.assertEqual(merged[0].listings, 7)

    def test_fallback_fills_missing_market_key(self) -> None:
        direct = snapshot("123", "Butterfly Knife | Fade", "Factory New", 1000, 7)
        fallback = snapshot("csgotrader:doppler", "Karambit | Doppler", "Minimal Wear", 850, 0)

        merged = merge_direct_and_fallback_snapshots([direct], [fallback])

        self.assertEqual(len(merged), 2)
        self.assertEqual({item.family for item in merged}, {"Butterfly Knife | Fade", "Karambit | Doppler"})


if __name__ == "__main__":
    unittest.main()
