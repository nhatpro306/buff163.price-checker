import unittest

import pandas as pd

from app_data_utils import filter_fallback_overrides_same_day


class FallbackListingMergeTests(unittest.TestCase):
    def test_same_day_fallback_row_is_dropped_when_direct_exists(self) -> None:
        history = pd.DataFrame(
            [
                {
                    "Timestamp": "2026-05-16 08:00:00",
                    "Family": "Butterfly Knife | Fade",
                    "Condition": "Factory New",
                    "Listings": 18,
                    "Buy Orders": 7,
                }
            ]
        )
        fallback = pd.DataFrame(
            [
                {
                    "Timestamp": "2026-05-16 12:00:00",
                    "Family": "Butterfly Knife | Fade",
                    "Condition": "Factory New",
                    "Listings": 0,
                    "Buy Orders": 0,
                },
                {
                    "Timestamp": "2026-05-16 12:00:00",
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


if __name__ == "__main__":
    unittest.main()
