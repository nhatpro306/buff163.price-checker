from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from market_config import HISTORY_HEADERS
from market_models import MarketSnapshot


class StorageBackendBase(ABC):
    """Minimal interface all storage backends must satisfy."""

    @abstractmethod
    def write_snapshots(self, snapshots: list[MarketSnapshot], timestamp: str) -> None:
        """Persist a batch of snapshots.  timestamp is ISO-8601 UTC string."""

    @abstractmethod
    def load_history_frame(self) -> pd.DataFrame:
        """Return a DataFrame with exactly the columns in HISTORY_HEADERS.

        Must return an empty DataFrame (not raise) when there is no data.
        """

    def empty_history_frame(self) -> pd.DataFrame:
        return pd.DataFrame(columns=HISTORY_HEADERS)
