from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def sample_history_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Timestamp": "2026-05-13 00:00:00",
                "Skin Name": "Karambit | Doppler (Factory New)",
                "Price": 1000.0,
                "Listings": 100,
            },
            {
                "Timestamp": "2026-05-14 00:00:00",
                "Skin Name": "Karambit | Doppler (Factory New)",
                "Price": 980.0,
                "Listings": 120,
            },
            {
                "Timestamp": "2026-05-15 00:00:00",
                "Skin Name": "Karambit | Doppler (Factory New)",
                "Price": 960.0,
                "Listings": 130,
            },
            {
                "Timestamp": "2026-05-16 00:00:00",
                "Skin Name": "Karambit | Doppler (Factory New)",
                "Price": 1040.0,
                "Listings": 80,
            },
            {
                "Timestamp": "2026-05-17 00:00:00",
                "Skin Name": "Karambit | Doppler (Factory New)",
                "Price": 1020.0,
                "Listings": 90,
            },
        ]
    )


@pytest.fixture
def mock_buff_response():
    def _factory(goods_id: str, price: float, listings: int) -> dict:
        return {
            "code": "OK",
            "data": {
                "items": [{"price": str(price)}],
                "total_count": listings,
                "goods_infos": {
                    str(goods_id): {
                        "market_hash_name": "Karambit | Doppler (Factory New)",
                        "steam_price_cny": str(price + 10),
                        "original_icon_url": "https://example.com/img.png",
                    }
                },
            },
        }

    return _factory
