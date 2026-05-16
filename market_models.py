from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketSnapshot:
    """One normalized market observation used by storage, charts, and tests."""

    goods_id: str
    family: str
    skin_name: str
    condition: str
    price: float
    listings: int
    buy_orders: int
    reference_price: float | None
    image_url: str
    observed_orders: int

    @property
    def knife_type(self) -> str:
        return self.family.split("|")[0].replace("★", "").strip()
