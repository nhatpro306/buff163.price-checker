from __future__ import annotations

import pandas as pd

from market_config import SHEET_NAME
from market_models import MarketSnapshot
from src.storage.base import StorageBackendBase
from src.storage.sheets import SheetStore, append_history, load_history_frame, rebuild_catalog


class SheetsStore(StorageBackendBase):
    def __init__(self, sheet_name: str = SHEET_NAME) -> None:
        self.sheet_name = sheet_name
        self._sheet_store: SheetStore | None = None

    def _get_sheet_store(self) -> SheetStore:
        if self._sheet_store is None:
            self._sheet_store = SheetStore(self.sheet_name)
        return self._sheet_store

    def write_snapshots(self, snapshots: list[MarketSnapshot], timestamp: str) -> None:
        store = self._get_sheet_store()
        rebuild_catalog(store, snapshots)
        append_history(store, snapshots, timestamp)

    def load_history_frame(self) -> pd.DataFrame:
        try:
            return load_history_frame(self._get_sheet_store())
        except Exception:
            return self.empty_history_frame()
