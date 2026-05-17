import unittest

import pandas as pd

from main import enrich_fallback_snapshots_with_latest_depth, merge_direct_and_fallback_snapshots
from market_models import MarketSnapshot


def snapshot(
    goods_id: str,
    family: str,
    condition: str,
    price: float,
    listings: int,
    buy_orders: int = 0,
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

    def test_fallback_depth_backfills_from_latest_history(self) -> None:
        fallback = snapshot("csgotrader:fade", "Butterfly Knife | Fade", "Factory New", 980, 0, 0)
        history = pd.DataFrame(
            [
                {
                    "Timestamp": "2026-05-14 00:00:00",
                    "Family": "Butterfly Knife | Fade",
                    "Condition": "Factory New",
                    "Listings": 5,
                    "Buy Orders": 2,
                },
                {
                    "Timestamp": "2026-05-15 00:00:00",
                    "Family": "Butterfly Knife | Fade",
                    "Condition": "Factory New",
                    "Listings": 9,
                    "Buy Orders": 4,
                },
            ]
        )

        enriched, filled_rows = enrich_fallback_snapshots_with_latest_depth([fallback], history)

        self.assertEqual(filled_rows, 1)
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0].listings, 9)
        self.assertEqual(enriched[0].buy_orders, 4)

    def test_depth_backfill_does_not_mutate_direct_snapshot_rows(self) -> None:
        direct = snapshot("123", "Butterfly Knife | Fade", "Factory New", 1000, 0, 0)
        history = pd.DataFrame(
            [
                {
                    "Timestamp": "2026-05-15 00:00:00",
                    "Family": "Butterfly Knife | Fade",
                    "Condition": "Factory New",
                    "Listings": 9,
                    "Buy Orders": 4,
                }
            ]
        )

        enriched, filled_rows = enrich_fallback_snapshots_with_latest_depth([direct], history)

        self.assertEqual(filled_rows, 0)
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0].goods_id, "123")
        self.assertEqual(enriched[0].listings, 0)
        self.assertEqual(enriched[0].buy_orders, 0)


if __name__ == "__main__":
    unittest.main()
