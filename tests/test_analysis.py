from __future__ import annotations

import pandas as pd

from main import PriceAnalysisAgent


def _df(prices, listings, name="Karambit | Doppler (Factory New)"):
    return pd.DataFrame(
        [
            {
                "Timestamp": f"2026-05-{i+1:02d} 00:00:00",
                "Skin Name": name,
                "Price": p,
                "Listings": listing_value,
            }
            for i, (p, listing_value) in enumerate(zip(prices, listings))
        ]
    )


def test_buy_watch_signal():
    df = _df([100, 100, 100, 94], [100, 100, 100, 130])
    s = PriceAnalysisAgent(df).summarize_skin("Karambit | Doppler (Factory New)")
    assert s and s["signal"] == "BUY_WATCH"


def test_sell_watch_signal():
    df = _df([100, 100, 100, 106], [120, 120, 120, 90])
    s = PriceAnalysisAgent(df).summarize_skin("Karambit | Doppler (Factory New)")
    assert s and s["signal"] == "SELL_WATCH"


def test_hold_signal():
    df = _df([100, 100, 100, 100], [100, 100, 100, 100])
    s = PriceAnalysisAgent(df).summarize_skin("Karambit | Doppler (Factory New)")
    assert s and s["signal"] == "ACCUMULATE"


def test_summarize_skin_empty(sample_history_df):
    assert PriceAnalysisAgent(sample_history_df).summarize_skin("No Skin") is None


def test_high_volatility():
    df = _df([100, 120, 80, 130, 90], [100, 100, 100, 100, 100])
    s = PriceAnalysisAgent(df).summarize_skin("Karambit | Doppler (Factory New)")
    assert s and s["signal"] == "HIGH_VOLATILITY"
