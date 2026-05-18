from __future__ import annotations

import pandas as pd

from market_config import CONDITION_ORDER
from market_models import MarketSnapshot
from market_utils import canonicalize_family_name


def merge_direct_and_fallback_snapshots(
    direct_snapshots: list[MarketSnapshot],
    fallback_snapshots: list[MarketSnapshot],
) -> list[MarketSnapshot]:
    """Merge direct BUFF rows with broad fallback price coverage.

    Direct BUFF rows are preferred because they include live listings and buy
    orders. Fallback rows fill price gaps for knives that the direct scan did
    not find during that scheduled run.
    """
    snapshots_by_market_key = {
        (snapshot.family, snapshot.condition): snapshot for snapshot in direct_snapshots
    }
    for snapshot in fallback_snapshots:
        # Fallback fills missing price rows only. Direct BUFF snapshots keep
        # richer live listing/buy-order data when both sources find a skin.
        snapshots_by_market_key.setdefault((snapshot.family, snapshot.condition), snapshot)
    return sorted(
        snapshots_by_market_key.values(),
        key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
    )


def merge_snapshots_with_full_catalog(
    primary_snapshots: list[MarketSnapshot],
    full_snapshots: list[MarketSnapshot],
) -> list[MarketSnapshot]:
    """Merge primary run snapshots with full-catalog depth rows.

    Primary rows (direct/fallback) stay the base, while full-catalog rows:
    - enrich listing/buy-order depth for the same Family+Condition keys
    - fill missing Family+Condition keys so all tracked knives appear
    """
    if not primary_snapshots:
        return sorted(
            full_snapshots,
            key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
        )
    if not full_snapshots:
        return sorted(
            primary_snapshots,
            key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
        )

    full_by_key: dict[tuple[str, str], MarketSnapshot] = {
        (snapshot.family, snapshot.condition): snapshot for snapshot in full_snapshots
    }
    merged: dict[tuple[str, str], MarketSnapshot] = {}

    for snapshot in primary_snapshots:
        key = (snapshot.family, snapshot.condition)
        full_snapshot = full_by_key.get(key)
        if full_snapshot is None:
            merged[key] = snapshot
            continue
        # Keep primary price source, but trust full-catalog for live depth.
        merged[key] = MarketSnapshot(
            goods_id=full_snapshot.goods_id or snapshot.goods_id,
            family=snapshot.family,
            skin_name=snapshot.skin_name,
            condition=snapshot.condition,
            price=snapshot.price,
            listings=full_snapshot.listings if full_snapshot.listings > 0 else snapshot.listings,
            buy_orders=(
                full_snapshot.buy_orders if full_snapshot.buy_orders > 0 else snapshot.buy_orders
            ),
            reference_price=(
                full_snapshot.reference_price
                if full_snapshot.reference_price is not None
                else snapshot.reference_price
            ),
            image_url=full_snapshot.image_url or snapshot.image_url,
            observed_orders=(
                full_snapshot.observed_orders
                if full_snapshot.observed_orders > 0
                else snapshot.observed_orders
            ),
        )

    for snapshot in full_snapshots:
        key = (snapshot.family, snapshot.condition)
        merged.setdefault(key, snapshot)

    return sorted(
        merged.values(),
        key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
    )


def enrich_fallback_snapshots_with_latest_depth(
    snapshots: list[MarketSnapshot],
    history: pd.DataFrame,
) -> tuple[list[MarketSnapshot], int]:
    """Backfill fallback listing/buy-order depth from latest known history.

    CSGOTrader fallback rows improve price coverage but do not provide live
    BUFF listing depth. For fallback-only rows, we reuse the latest known
    listing/buy-order values for the same market key (family + condition).
    """
    if not snapshots or history.empty:
        return snapshots, 0

    required_cols = {"Timestamp", "Family", "Condition", "Listings"}
    if not required_cols.issubset(set(history.columns)):
        return snapshots, 0

    frame = history.copy()
    frame["Timestamp"] = pd.to_datetime(frame["Timestamp"], errors="coerce", utc=True)
    frame["Family"] = frame["Family"].fillna("").astype(str).map(canonicalize_family_name)
    frame["Condition"] = frame["Condition"].fillna("Unknown").astype(str)
    frame["Listings"] = pd.to_numeric(frame["Listings"], errors="coerce")
    frame["Buy Orders"] = pd.to_numeric(frame.get("Buy Orders"), errors="coerce").fillna(0)
    frame = frame.dropna(subset=["Timestamp", "Family", "Condition", "Listings"]).sort_values(
        "Timestamp"
    )
    if frame.empty:
        return snapshots, 0

    latest_by_key: dict[tuple[str, str], tuple[int, int]] = {}
    for row in frame[["Family", "Condition", "Listings", "Buy Orders"]].itertuples(index=False):
        listings = max(0, int(round(float(row[2]))))
        buy_orders = max(0, int(round(float(row[3]))))
        if listings <= 0 and buy_orders <= 0:
            continue
        latest_by_key[(row[0], row[1])] = (listings, buy_orders)
    if not latest_by_key:
        return snapshots, 0

    enriched_snapshots: list[MarketSnapshot] = []
    filled_rows = 0
    for snapshot in snapshots:
        if not snapshot.goods_id.startswith("csgotrader:"):
            enriched_snapshots.append(snapshot)
            continue
        needs_listings = snapshot.listings <= 0
        needs_buy_orders = snapshot.buy_orders <= 0
        if not (needs_listings or needs_buy_orders):
            enriched_snapshots.append(snapshot)
            continue

        key = (canonicalize_family_name(snapshot.family), snapshot.condition)
        depth = latest_by_key.get(key)
        if depth is None:
            enriched_snapshots.append(snapshot)
            continue

        listings, buy_orders = depth
        updated = MarketSnapshot(
            goods_id=snapshot.goods_id,
            family=snapshot.family,
            skin_name=snapshot.skin_name,
            condition=snapshot.condition,
            price=snapshot.price,
            listings=listings if needs_listings else snapshot.listings,
            buy_orders=buy_orders if needs_buy_orders else snapshot.buy_orders,
            reference_price=snapshot.reference_price,
            image_url=snapshot.image_url,
            observed_orders=snapshot.observed_orders,
        )
        if updated.listings != snapshot.listings or updated.buy_orders != snapshot.buy_orders:
            filled_rows += 1
        enriched_snapshots.append(updated)
    return enriched_snapshots, filled_rows
