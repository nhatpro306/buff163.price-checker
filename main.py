from __future__ import annotations

import time  # noqa: F401

from market_config import ALL_CATALOG_HEADERS as ALL_CATALOG_HEADERS
from market_config import ALL_CATALOG_SHEET_NAME as ALL_CATALOG_SHEET_NAME
from market_config import CATALOG_HEADERS as CATALOG_HEADERS
from market_config import CATALOG_SHEET_NAME as CATALOG_SHEET_NAME
from market_config import CONDITION_ORDER as CONDITION_ORDER
from market_config import DEFAULT_KNIFE_CATEGORIES as DEFAULT_KNIFE_CATEGORIES
from market_config import DEFAULT_TRACK_KEYWORDS as DEFAULT_TRACK_KEYWORDS
from market_config import FORECAST_SHEET_NAME as FORECAST_SHEET_NAME
from market_config import SHEET_NAME as SHEET_NAME
from src.analysis import PriceAnalysisAgent as PriceAnalysisAgent
from src.cli import main as cli_main
from src.client import BuffPriceClient as BuffPriceClient
from src.etl import normalize_history_values as normalize_history_values
from src.etl import parse_family_and_condition as parse_family_and_condition
from src.orchestrator import run as run
from src.settings import get_search_keywords as get_search_keywords
from src.settings import get_seed_goods_ids as get_seed_goods_ids
from src.snapshot_merge import (
    enrich_fallback_snapshots_with_latest_depth as enrich_fallback_snapshots_with_latest_depth,
)
from src.snapshot_merge import (
    merge_direct_and_fallback_snapshots as merge_direct_and_fallback_snapshots,
)
from src.snapshot_merge import (
    merge_snapshots_with_full_catalog as merge_snapshots_with_full_catalog,
)
from src.storage import SheetStore as SheetStore
from src.storage import append_history as append_history
from src.storage import csgotrader_snapshots as csgotrader_snapshots
from src.storage import load_history_frame as load_history_frame
from src.storage import migrate_history_sheet as migrate_history_sheet
from src.storage import rebuild_all_catalog as rebuild_all_catalog
from src.storage import rebuild_catalog as rebuild_catalog
from src.storage import rebuild_dashboard as rebuild_dashboard
from src.storage import rebuild_forecast as rebuild_forecast
from src.storage import rebuild_signals as rebuild_signals
from src.storage import sqlite_connect as sqlite_connect
from src.storage import sqlite_init as sqlite_init
from src.storage import sqlite_load_history_frame as sqlite_load_history_frame
from src.storage import sqlite_upsert_snapshot as sqlite_upsert_snapshot
from src.storage import sqlite_write_snapshots as sqlite_write_snapshots

__all__ = [
    "ALL_CATALOG_HEADERS",
    "ALL_CATALOG_SHEET_NAME",
    "CATALOG_HEADERS",
    "CATALOG_SHEET_NAME",
    "CONDITION_ORDER",
    "DEFAULT_KNIFE_CATEGORIES",
    "DEFAULT_TRACK_KEYWORDS",
    "FORECAST_SHEET_NAME",
    "SHEET_NAME",
    "BuffPriceClient",
    "PriceAnalysisAgent",
    "SheetStore",
    "append_history",
    "csgotrader_snapshots",
    "load_history_frame",
    "migrate_history_sheet",
    "normalize_history_values",
    "parse_family_and_condition",
    "rebuild_all_catalog",
    "rebuild_catalog",
    "rebuild_dashboard",
    "rebuild_forecast",
    "rebuild_signals",
    "sqlite_connect",
    "sqlite_init",
    "sqlite_load_history_frame",
    "sqlite_upsert_snapshot",
    "sqlite_write_snapshots",
]


if __name__ == "__main__":
    cli_main()
