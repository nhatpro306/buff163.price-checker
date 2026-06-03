from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from src.storage.base import StorageBackendBase as StorageBackendBase
from src.storage.credentials import credentials_from_info as credentials_from_info
from src.storage.credentials import load_google_credentials as load_google_credentials
from src.storage.credentials import resolve_credentials_path as resolve_credentials_path
from src.storage.factory import StorageBackend as StorageBackend
from src.storage.factory import get_storage_backend as get_storage_backend
from src.storage.sheets import SheetStore as SheetStore
from src.storage.sheets import append_history as append_history
from src.storage.sheets import csgotrader_snapshots as csgotrader_snapshots
from src.storage.sheets import get_track_keywords as get_track_keywords
from src.storage.sheets import load_history_frame as load_history_frame
from src.storage.sheets import migrate_history_sheet as migrate_history_sheet
from src.storage.sheets import rebuild_all_catalog as rebuild_all_catalog
from src.storage.sheets import rebuild_catalog as rebuild_catalog
from src.storage.sheets import rebuild_dashboard as rebuild_dashboard
from src.storage.sheets import rebuild_forecast as rebuild_forecast
from src.storage.sheets import rebuild_signals as rebuild_signals
from src.storage.sheets_store import SheetsStore as SheetsStore
from src.storage.sqlite import sqlite_connect as sqlite_connect
from src.storage.sqlite import sqlite_init as sqlite_init
from src.storage.sqlite import sqlite_load_history_frame as sqlite_load_history_frame
from src.storage.sqlite import sqlite_upsert_snapshot as sqlite_upsert_snapshot
from src.storage.sqlite import sqlite_write_snapshots as sqlite_write_snapshots
from src.storage.sqlite_store import SqliteStore as SqliteStore

try:
    from src.storage.postgres_store import PostgresStore as PostgresStore
except ImportError:  # pragma: no cover - psycopg2 optional
    PostgresStore = None  # type: ignore[assignment,misc]


class PageMetaCache:
    def __init__(self, db_path: str = "page_meta_cache.sqlite3") -> None:
        self.db_path = db_path
        self._init()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS page_meta (
                    goods_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                )
                """)

    def get(self, goods_id: str, max_age_hours: int = 48):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data, fetched_at FROM page_meta WHERE goods_id = ?",
                (goods_id,),
            ).fetchone()
        if not row:
            return None
        fetched_at = datetime.fromisoformat(row[1])
        if (datetime.now(UTC) - fetched_at).total_seconds() > max_age_hours * 3600:
            return None
        return json.loads(row[0])

    def set(self, goods_id: str, data: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO page_meta(goods_id, data, fetched_at) VALUES(?,?,?)",
                (goods_id, json.dumps(data), datetime.now(UTC).isoformat()),
            )


__all__ = [
    "PageMetaCache",
    "StorageBackend",
    "StorageBackendBase",
    "get_storage_backend",
    "SheetsStore",
    "SqliteStore",
    "PostgresStore",
    "SheetStore",
    "append_history",
    "credentials_from_info",
    "csgotrader_snapshots",
    "get_track_keywords",
    "load_google_credentials",
    "load_history_frame",
    "migrate_history_sheet",
    "rebuild_all_catalog",
    "rebuild_catalog",
    "rebuild_dashboard",
    "rebuild_forecast",
    "rebuild_signals",
    "resolve_credentials_path",
    "sqlite_connect",
    "sqlite_init",
    "sqlite_load_history_frame",
    "sqlite_upsert_snapshot",
    "sqlite_write_snapshots",
]
