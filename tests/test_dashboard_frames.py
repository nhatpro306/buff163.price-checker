from __future__ import annotations

import pandas as pd

from market_config import HISTORY_HEADERS
from src.dashboard.frames import load_app_frames


def test_load_app_frames_uses_configured_postgres_backend():
    history = pd.DataFrame(columns=HISTORY_HEADERS)

    out = load_app_frames(
        storage_backend="postgres",
        use_sqlite=False,
        sqlite_path="",
        load_backend_history=lambda: history,
        load_sqlite_history=lambda _path: (_ for _ in ()).throw(AssertionError("no sqlite")),
        load_sheet_history=lambda: (_ for _ in ()).throw(AssertionError("no sheets")),
        load_sheet_records=lambda _name: pd.DataFrame(),
        catalog_sheet_name="catalog",
        all_catalog_sheet_name="all",
        forecast_sheet_name="forecast",
    )

    history_df, catalog_df, all_catalog_df, forecast_df, startup_error = out
    assert startup_error is None
    assert history_df is history
    assert catalog_df.empty
    assert all_catalog_df.empty
    assert forecast_df.empty
