from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from main import (
    SheetStore,
    credentials_from_info,
    load_google_credentials,
    resolve_credentials_path,
    sqlite_load_history_frame,
    sqlite_write_snapshots,
)


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
    "SheetStore",
    "PageMetaCache",
    "credentials_from_info",
    "load_google_credentials",
    "resolve_credentials_path",
    "sqlite_load_history_frame",
    "sqlite_write_snapshots",
]
