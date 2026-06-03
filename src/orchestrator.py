from __future__ import annotations

import os
from datetime import UTC, datetime

from market_config import DEFAULT_SQLITE_PATH, SHEET_NAME
from market_models import MarketSnapshot
from market_utils import debug_log, env_flag
from src.analysis import PriceAnalysisAgent
from src.client import BuffPriceClient
from src.results import ITEM_SKIPPED, ITEM_SUCCESS, ScrapeItemResult, ScrapeRunSummary
from src.settings import get_search_keywords, get_seed_goods_ids
from src.snapshot_merge import (
    enrich_fallback_snapshots_with_latest_depth,
    merge_direct_and_fallback_snapshots,
    merge_snapshots_with_full_catalog,
)
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
from src.validation import validate_snapshot


def run(migrate_only: bool = False) -> ScrapeRunSummary | None:
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
    debug_log(
        f"pipeline history_loaded rows={len(history)} source={'sheets' if store is not None else 'sqlite'}"
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
        return None

    client = BuffPriceClient()
    run_summary = ScrapeRunSummary.start()
    run_summary.storage_backend = os.getenv("STORAGE_BACKEND", "sheets").strip().lower()
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
        debug_log(
            "pipeline direct_complete "
            f"snapshots={len(snapshots)} distinct_goods={len({s.goods_id for s in snapshots})}"
        )
    if env_flag("BUFF_FALLBACK_CSGOTRADER", False):
        fallback_snapshots = csgotrader_snapshots(track_keywords, min_price)
        debug_log(
            "pipeline fallback_raw "
            f"snapshots={len(fallback_snapshots)} distinct_goods={len({s.goods_id for s in fallback_snapshots})}"
        )
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
        debug_log(
            "pipeline fallback_merged "
            f"direct={direct_count} fallback={len(fallback_snapshots)} "
            f"final={len(snapshots)}"
        )
        print(
            f"Fallback merge: direct={direct_count}, "
            f"fallback={len(fallback_snapshots)}, final={len(snapshots)}."
        )

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
        before_full_merge = len(snapshots)
        snapshots = merge_snapshots_with_full_catalog(snapshots, full_snapshots)
        debug_log(
            "pipeline full_catalog_merged "
            f"primary={before_full_merge} full={len(full_snapshots)} final={len(snapshots)}"
        )
        if store is not None:
            rebuild_all_catalog(store, full_snapshots, timestamp)

    # Validate business data after a successful fetch. Malformed snapshots are
    # skipped (logged, not stored) so one bad goods_id never poisons storage.
    valid_snapshots: list[MarketSnapshot] = []
    for snapshot in snapshots:
        problems = validate_snapshot(snapshot)
        if problems:
            reason = "; ".join(problems)
            run_summary.record(
                ScrapeItemResult(
                    goods_id=snapshot.goods_id,
                    status=ITEM_SKIPPED,
                    error_type="validation",
                    error_message=reason,
                )
            )
            debug_log(f"pipeline skip_invalid goods_id={snapshot.goods_id} reason={reason}")
            continue
        run_summary.record(
            ScrapeItemResult(
                goods_id=snapshot.goods_id,
                status=ITEM_SUCCESS,
                item_name=snapshot.skin_name,
                price=snapshot.price,
                listing_count=snapshot.listings,
                scraped_at=timestamp,
            )
        )
        valid_snapshots.append(snapshot)
    snapshots = valid_snapshots

    if enable_sqlite and sqlite_path and write_sheets:
        sqlite_write_snapshots(sqlite_path, snapshots, timestamp)

    if not write_sheets:
        if enable_sqlite and sqlite_path:
            sqlite_write_snapshots(sqlite_path, snapshots, timestamp)
        print(
            f"Collected {len(snapshots)} high-value snapshots for {', '.join(track_keywords)} "
            f"(>= {min_price:.0f} CNY, pages={high_value_pages})."
        )
        run_summary.finalize()
        print(run_summary.log_line())
        return run_summary

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
    run_summary.finalize()
    print(run_summary.log_line())
    return run_summary
