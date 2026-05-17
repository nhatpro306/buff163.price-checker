import unittest

import pandas as pd

from app_data_utils import (
    apply_analytics_filters,
    build_listing_data_table,
    build_overview_metrics,
    build_price_history_frame,
    build_recent_points_table,
    build_sell_history_table,
    build_variant_daily_frame,
    build_variant_metrics,
    filter_fallback_overrides_same_day,
    infer_dashboard_columns,
)


class AppDataUtilsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.variant_df = pd.DataFrame(
            [
                {
                    "Timestamp": "2026-05-15 00:00:00",
                    "Price": 1000.0,
                    "Condition": "Factory New",
                    "Listings": 5,
                    "Buy Orders": 2,
                    "Reference Price": 1100.0,
                    "Observed Orders": 3,
                },
                {
                    "Timestamp": "2026-05-15 12:00:00",
                    "Price": 1020.0,
                    "Condition": "Factory New",
                    "Listings": 0,
                    "Buy Orders": 4,
                    "Reference Price": None,
                    "Observed Orders": 2,
                },
                {
                    "Timestamp": "2026-05-16 00:00:00",
                    "Price": 990.0,
                    "Condition": "Minimal Wear",
                    "Listings": 7,
                    "Buy Orders": 5,
                    "Reference Price": 995.0,
                    "Observed Orders": 1,
                },
            ]
        )
        self.variant_df["Timestamp"] = pd.to_datetime(self.variant_df["Timestamp"], utc=True)

    def test_build_variant_daily_frame(self) -> None:
        daily = build_variant_daily_frame(self.variant_df)
        self.assertEqual(list(daily.columns), ["Day", "Price", "Listings", "BuyOrders"])
        self.assertEqual(len(daily), 2)
        # 2026-05-15 average price = (1000 + 1020) / 2
        day0 = daily.iloc[0]
        self.assertAlmostEqual(float(day0["Price"]), 1010.0, places=4)

    def test_build_recent_points_table(self) -> None:
        summary = build_recent_points_table(self.variant_df, limit=2)
        self.assertEqual(len(summary), 2)
        self.assertIn("Timestamp", summary.columns)
        self.assertTrue(summary["Listings"].dtype.kind in {"i", "u"})
        self.assertTrue(summary["Buy Orders"].dtype.kind in {"i", "u"})

    def test_build_sell_history_table(self) -> None:
        sell_view = build_sell_history_table(self.variant_df)
        self.assertEqual(len(sell_view), 3)
        self.assertTrue(sell_view["Observed Orders"].dtype.kind in {"i", "u"})

    def test_build_variant_metrics(self) -> None:
        metrics = build_variant_metrics(self.variant_df.sort_values("Timestamp"))
        self.assertEqual(int(metrics["buy_orders"]), 5)
        self.assertEqual(int(metrics["sell_stock"]), 7)
        self.assertAlmostEqual(float(metrics["reference_price"]), 995.0, places=4)
        self.assertTrue(pd.notna(metrics["last_update"]))

    def test_build_variant_metrics_empty(self) -> None:
        metrics = build_variant_metrics(pd.DataFrame())
        self.assertIsNone(metrics["latest_price"])
        self.assertEqual(metrics["buy_orders"], 0)
        self.assertEqual(metrics["sell_stock"], 0)

    def test_filter_fallback_overrides_same_day(self) -> None:
        history = pd.DataFrame(
            [
                {
                    "Timestamp": "2026-05-17 00:10:00",
                    "Family": "Butterfly Knife | Fade",
                    "Condition": "Factory New",
                    "Listings": 15,
                    "Buy Orders": 5,
                }
            ]
        )
        fallback = pd.DataFrame(
            [
                {
                    "Timestamp": "2026-05-17 12:00:00",
                    "Family": "Butterfly Knife | Fade",
                    "Condition": "Factory New",
                    "Listings": 0,
                    "Buy Orders": 0,
                },
                {
                    "Timestamp": "2026-05-17 12:00:00",
                    "Family": "Karambit | Doppler",
                    "Condition": "Minimal Wear",
                    "Listings": 0,
                    "Buy Orders": 0,
                },
            ]
        )

        kept = filter_fallback_overrides_same_day(history, fallback)

        self.assertEqual(len(kept), 1)
        self.assertEqual(str(kept.iloc[0]["Family"]), "Karambit | Doppler")

    def test_infer_dashboard_columns(self) -> None:
        cols = infer_dashboard_columns(self.variant_df)
        self.assertEqual(cols["price"], "Price")
        self.assertEqual(cols["timestamp"], "Timestamp")
        self.assertEqual(cols["condition"], "Condition")

    def test_apply_analytics_filters(self) -> None:
        frame = self.variant_df.copy()
        frame["Skin Name"] = ["A", "A", "B"]
        frame["Condition"] = ["Factory New", "Factory New", "Minimal Wear"]
        filtered = apply_analytics_filters(
            frame,
            skin_col="Skin Name",
            condition_col="Condition",
            timestamp_col="Timestamp",
            skin_value="A",
            condition_value="Factory New",
            date_start=pd.Timestamp("2026-05-15"),
            date_end=pd.Timestamp("2026-05-15"),
        )
        self.assertEqual(len(filtered), 2)

    def test_build_overview_metrics(self) -> None:
        metrics = build_overview_metrics(self.variant_df, price_col="Price", timestamp_col="Timestamp")
        self.assertAlmostEqual(metrics["latest"], 990.0, places=4)
        self.assertAlmostEqual(metrics["average"], (1000.0 + 1020.0 + 990.0) / 3, places=4)
        self.assertAlmostEqual(metrics["highest"], 1020.0, places=4)
        self.assertAlmostEqual(metrics["lowest"], 990.0, places=4)
        self.assertIsNotNone(metrics["change_pct"])

    def test_build_price_history_frame(self) -> None:
        trend = build_price_history_frame(self.variant_df, price_col="Price", timestamp_col="Timestamp")
        self.assertEqual(list(trend.columns), ["Date", "Price"])
        self.assertEqual(len(trend), 2)

    def test_build_listing_data_table(self) -> None:
        table = build_listing_data_table(
            self.variant_df,
            timestamp_col="Timestamp",
            price_col="Price",
            listings_col="Listings",
            buy_orders_col="Buy Orders",
        )
        self.assertEqual(len(table), 3)
        self.assertIn("Price", table.columns)
        self.assertIn("Listings", table.columns)


if __name__ == "__main__":
    unittest.main()
