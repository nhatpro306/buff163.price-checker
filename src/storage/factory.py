from __future__ import annotations

import os
from enum import Enum

from src.storage.base import StorageBackendBase


class StorageBackend(str, Enum):
    SHEETS = "sheets"
    SQLITE = "sqlite"
    POSTGRES = "postgres"


def get_storage_backend() -> StorageBackendBase:
    """Return the active storage backend based on STORAGE_BACKEND env var.

    Defaults to "sheets" so existing deployments are unaffected.
    Valid values: sheets | sqlite | postgres
    """
    raw = os.getenv("STORAGE_BACKEND", "sheets").strip().lower()

    try:
        backend = StorageBackend(raw)
    except ValueError:
        print(
            f"Unknown STORAGE_BACKEND={raw!r}. "
            f"Valid options: {[b.value for b in StorageBackend]}. "
            "Falling back to 'sheets'."
        )
        backend = StorageBackend.SHEETS

    if backend is StorageBackend.POSTGRES:
        from src.storage.postgres_store import PostgresStore  # noqa: PLC0415
        return PostgresStore()

    if backend is StorageBackend.SQLITE:
        sqlite_path = os.getenv("BUFF_SQLITE_PATH", "buff163.sqlite3").strip()
        if not sqlite_path:
            raise ValueError(
                "BUFF_SQLITE_PATH must be set when STORAGE_BACKEND=sqlite"
            )
        from src.storage.sqlite_store import SqliteStore  # noqa: PLC0415
        return SqliteStore(sqlite_path)

    # default: sheets
    sheet_name = os.getenv("BUFF_SHEET_NAME", "").strip()
    from src.storage.sheets_store import SheetsStore  # noqa: PLC0415
    return SheetsStore(sheet_name or None)
