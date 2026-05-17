from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any

import pandas as pd


class PriceAnalysisAgent:
    def __init__(self, history: pd.DataFrame) -> None:
        self.history = history.copy()
        if not self.history.empty:
            self.history["Timestamp"] = pd.to_datetime(
                self.history["Timestamp"], errors="coerce", utc=True
            )
            self.history["Price"] = pd.to_numeric(self.history["Price"], errors="coerce")
            self.history["Listings"] = pd.to_numeric(self.history["Listings"], errors="coerce")
            self.history = self.history.dropna(
                subset=["Timestamp", "Skin Name", "Price", "Listings"]
            )

    def summarize_skin(self, skin_name: str) -> dict[str, Any] | None:
        skin_history = self.history[self.history["Skin Name"] == skin_name].sort_values("Timestamp")
        if skin_history.empty:
            return None

        prices = skin_history["Price"].tolist()
        listings = skin_history["Listings"].tolist()
        latest_price = prices[-1]
        baseline_price = mean(prices[:-1]) if len(prices) > 1 else latest_price
        avg_price = mean(prices)
        min_price = min(prices)
        max_price = max(prices)
        price_stddev = pstdev(prices) if len(prices) > 1 else 0.0
        volatility_pct = (price_stddev / avg_price * 100) if avg_price else 0.0
        price_change_pct = (
            ((latest_price - baseline_price) / baseline_price * 100) if baseline_price else 0.0
        )
        listing_avg = mean(listings)
        latest_listings = listings[-1]
        listing_pressure_pct = (
            ((latest_listings - listing_avg) / listing_avg * 100) if listing_avg else 0.0
        )

        signal, confidence, rationale = self._classify(
            latest_price=latest_price,
            avg_price=avg_price,
            min_price=min_price,
            max_price=max_price,
            latest_listings=latest_listings,
            listing_avg=listing_avg,
            volatility_pct=volatility_pct,
        )

        return {
            "skin_name": skin_name,
            "latest_price": round(latest_price, 2),
            "average_price": round(avg_price, 2),
            "min_price": round(min_price, 2),
            "max_price": round(max_price, 2),
            "price_change_pct": round(price_change_pct, 2),
            "volatility_pct": round(volatility_pct, 2),
            "latest_listings": int(latest_listings),
            "listing_pressure_pct": round(listing_pressure_pct, 2),
            "signal": signal,
            "confidence": round(confidence, 2),
            "rationale": rationale,
            "data_points": len(prices),
        }

    def _classify(
        self,
        *,
        latest_price: float,
        avg_price: float,
        min_price: float,
        max_price: float,
        latest_listings: float,
        listing_avg: float,
        volatility_pct: float,
    ) -> tuple[str, float, str]:
        undervalued = latest_price < avg_price * 0.97
        overvalued = latest_price > avg_price * 1.03
        listing_spike = latest_listings > listing_avg * 1.1 if listing_avg else False
        listing_drop = latest_listings < listing_avg * 0.9 if listing_avg else False
        near_floor = (
            math.isclose(latest_price, min_price, rel_tol=0.01) or latest_price <= min_price * 1.03
        )
        near_ceiling = (
            math.isclose(latest_price, max_price, rel_tol=0.01) or latest_price >= max_price * 0.97
        )

        if undervalued and listing_spike:
            return ("BUY_WATCH", 0.79, "Price is below its average while stock is elevated.")
        if overvalued and listing_drop:
            return (
                "SELL_WATCH",
                0.76,
                "Price is above its average while sell-side stock is tightening.",
            )
        if near_floor:
            return ("ACCUMULATE", 0.67, "Price is near the observed floor for this condition.")
        if near_ceiling:
            return ("TAKE_PROFIT", 0.66, "Price is near the observed ceiling for this condition.")
        if volatility_pct >= 8:
            return ("HIGH_VOLATILITY", 0.58, "Price swings are elevated relative to the average.")
        return ("HOLD", 0.45, "Current price and listing depth are near the recent baseline.")
