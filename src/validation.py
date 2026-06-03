"""Business-data validation for scraped snapshots.

Runs after a successful HTTP response. Malformed data is skipped (not retried)
so one bad goods_id never poisons storage or fails a whole run.
"""

from __future__ import annotations

from market_models import MarketSnapshot


def validate_snapshot(snapshot: MarketSnapshot) -> list[str]:
    """Return a list of human-readable problems. Empty list means valid."""
    errors: list[str] = []

    if not str(snapshot.goods_id).strip():
        errors.append("empty goods_id")

    price = snapshot.price
    # bool is a subclass of int; reject it explicitly.
    if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
        errors.append(f"price must be a number > 0 (got {price!r})")

    listings = snapshot.listings
    if isinstance(listings, bool) or not isinstance(listings, int) or listings < 0:
        errors.append(f"listings must be an integer >= 0 (got {listings!r})")

    if not str(snapshot.skin_name).strip():
        errors.append("empty skin_name")

    return errors


def is_valid_snapshot(snapshot: MarketSnapshot) -> bool:
    return not validate_snapshot(snapshot)


__all__ = ["validate_snapshot", "is_valid_snapshot"]
