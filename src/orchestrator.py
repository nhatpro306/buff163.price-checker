from __future__ import annotations

import os
from datetime import UTC, datetime

import pandas as pd

from market_config import (
    CONDITION_ORDER,
    DEFAULT_KNIFE_CATEGORIES,
    DEFAULT_KNIFE_FINISHES,
    DEFAULT_SQLITE_PATH,
    SHEET_NAME,
)
from market_models import MarketSnapshot
from market_utils import canonicalize_family_name, env_flag
from src.analysis import PriceAnalysisAgent
from src.client import BuffPriceClient
from src.storage import (
    SheetStore,
    append_history,
    csgotrader_snapshots,
    get_track_keywords,
    load_history_frame,
    migrate_history_sheet,
    rebuild_all_catalog,
    rebuild_catalog,
    rebuild_dashboard,
    rebuild_forecast,
    rebuild_signals,
    sqlite_load_history_frame,
    sqlite_write_snapshots,
)


def get_seed_goods_ids() -> list[str]:
    raw = os.getenv("BUFF_SEED_GOODS_IDS")
    if raw is not None:
        return [item.strip() for item in raw.split(",") if item.strip()]
    legacy_raw = os.getenv("BUFF_BUTTERFLY_SEEDS")
    if legacy_raw:
        return [item.strip() for item in legacy_raw.split(",") if item.strip()]
    return []


def get_search_keywords(track_keywords: list[str]) -> list[str | tuple[str, str | None]]:
    raw = os.getenv("BUFF_SEARCH_KEYWORDS")
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    expand_finishes = env_flag("BUFF_EXPAND_FINISH_SEARCHES", False)
    searches: list[str | tuple[str, str | None]] = []
    for knife in track_keywords:
        category = DEFAULT_KNIFE_CATEGORIES.get(knife)
        searches.append((knife, category))
        if expand_finishes:
            searches.extend((finish, category) for finish in DEFAULT_KNIFE_FINISHES)
    return searches


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


def run(migrate_only: bool = False) -> None:
    sqlite_path = os.getenv("BUFF_SQLITE_PATH", DEFAULT_SQLITE_PATH).strip()
    enable_sqlite = env_flag("BUFF_WRITE_SQLITE", False)
    write_sheets = env_flag("BUFF_WRITE_SHEETS", not enable_sqlite)
    store = (
        SheetStore(SHEET_NAME)
        if write_sheets or migrate_only or env_flag("BUFF_RUN_MIGRATION", False)
        else None
    )
    run_migration = migrate_only or env_flag("BUFF_RUN_MIGRATION", False)
    if run_migration:
        if store is None:
            raise ValueError("Sheet migration requires Google Sheets.")
        migrated_rows = migrate_history_sheet(store)
        if migrated_rows:
            print(f"Migrated {migrated_rows} history rows to the current schema.")
    else:
        print("Skipping migration for this run (BUFF_RUN_MIGRATION is disabled).")

    history = (
        load_history_frame(store) if store is not None else sqlite_load_history_frame(sqlite_path)
    )
    if migrate_only:
        agent = PriceAnalysisAgent(history)
        tracked_names = sorted(history["Skin Name"].dropna().unique().tolist())
        analysis_rows = [
            summary for name in tracked_names if (summary := agent.summarize_skin(name))
        ]
        if store is None:
            raise ValueError("Migration-only run requires Google Sheets.")
        rebuild_dashboard(store, analysis_rows)
        rebuild_signals(store, analysis_rows, datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"))
        if env_flag("BUFF_ENABLE_FORECAST", True):
            rebuild_forecast(store, history)
        print("Migration-only run completed.")
        return

    client = BuffPriceClient()
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    min_price = float(os.getenv("BUFF_MIN_PRICE_CNY", "0"))
    try:
        high_value_pages = max(1, int(os.getenv("BUFF_HIGH_VALUE_PAGES", "25")))
    except ValueError:
        high_value_pages = 25
    track_keywords = get_track_keywords()
    search_keywords = get_search_keywords(track_keywords)
    snapshots: list[MarketSnapshot] = []
    if not env_flag("BUFF_SKIP_DIRECT", False):
        max_goods_raw = os.getenv("BUFF_MAX_GOODS_PER_RUN", "").strip()
        max_goods = int(max_goods_raw) if max_goods_raw else None
        snapshots = client.discover_high_value_catalog(
            keywords=search_keywords,
            min_price=min_price,
            seed_goods_ids=get_seed_goods_ids(),
            max_pages_per_keyword=high_value_pages,
            match_keywords=track_keywords,
            max_goods=max_goods,
            on_snapshot=(
                (lambda snapshot: sqlite_write_snapshots(sqlite_path, [snapshot], timestamp))
                if enable_sqlite and sqlite_path and not write_sheets
                else None
            ),
        )
    if env_flag("BUFF_FALLBACK_CSGOTRADER", False):
        fallback_snapshots = csgotrader_snapshots(track_keywords, min_price)
        fallback_snapshots, backfilled_rows = enrich_fallback_snapshots_with_latest_depth(
            fallback_snapshots, history
        )
        if backfilled_rows:
            print(f"Fallback depth backfill: {backfilled_rows} rows reused latest listing depth.")
        min_fallback_snapshots = int(os.getenv("BUFF_MIN_FALLBACK_SNAPSHOTS", "0") or "0")
        if min_fallback_snapshots and len(fallback_snapshots) < min_fallback_snapshots:
            # A tiny fallback result would silently create missing price days.
            # Failing the workflow is safer because GitHub Actions will show it.
            raise RuntimeError(
                "Fallback source returned too few tracked snapshots: "
                f"{len(fallback_snapshots)} < {min_fallback_snapshots}."
            )
        direct_count = len(snapshots)
        snapshots = merge_direct_and_fallback_snapshots(snapshots, fallback_snapshots)
        print(
            f"Fallback merge: direct={direct_count}, "
            f"fallback={len(fallback_snapshots)}, final={len(snapshots)}."
        )
        if enable_sqlite and sqlite_path and not write_sheets:
            sqlite_write_snapshots(sqlite_path, fallback_snapshots, timestamp)

    full_catalog_enabled = os.getenv("BUFF_FULL_CATALOG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if full_catalog_enabled:
        max_pages = int(os.getenv("BUFF_FULL_CATALOG_PAGES", "60"))
        full_snapshots = client.discover_full_catalog(
            keywords=search_keywords,
            seed_goods_ids=get_seed_goods_ids(),
            max_pages_per_keyword=max_pages,
            match_keywords=track_keywords,
        )
        snapshots = merge_snapshots_with_full_catalog(snapshots, full_snapshots)
        if store is not None:
            rebuild_all_catalog(store, full_snapshots, timestamp)

    if enable_sqlite and sqlite_path and write_sheets:
        sqlite_write_snapshots(sqlite_path, snapshots, timestamp)

    if not write_sheets:
        print(
            f"Collected {len(snapshots)} high-value snapshots for {', '.join(track_keywords)} "
            f"(>= {min_price:.0f} CNY, pages={high_value_pages})."
        )
        return

    if store is None:
        raise ValueError("Google Sheets output is enabled but no sheet store is configured.")
    rebuild_catalog(store, snapshots)
    append_history(store, snapshots, timestamp)

    history = load_history_frame(store)
    agent = PriceAnalysisAgent(history)
    tracked_names = sorted(set(history["Skin Name"].dropna().unique().tolist()))
    analysis_rows = [summary for name in tracked_names if (summary := agent.summarize_skin(name))]

    rebuild_dashboard(store, analysis_rows)
    rebuild_signals(store, analysis_rows, timestamp)
    if env_flag("BUFF_ENABLE_FORECAST", False):
        rebuild_forecast(store, history)
    print(
        f"Collected {len(snapshots)} high-value snapshots for {', '.join(track_keywords)} "
        f"(>= {min_price:.0f} CNY, pages={high_value_pages})."
    )
