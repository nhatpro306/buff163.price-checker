from __future__ import annotations

import pandas as pd

from market_models import MarketSnapshot
from src.storage.base import StorageBackendBase
from src.storage.sqlite import (
    sqlite_load_history_frame as _load,
)
from src.storage.sqlite import (
    sqlite_write_snapshots as _write,
)


class SqliteStore(StorageBackendBase):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def write_snapshots(self, snapshots: list[MarketSnapshot], timestamp: str) -> None:
        _write(self.db_path, snapshots, timestamp)

    def load_history_frame(self) -> pd.DataFrame:
        return _load(self.db_path)
