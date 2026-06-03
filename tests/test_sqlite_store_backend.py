from __future__ import annotations

import pandas as pd

from market_config import HISTORY_HEADERS
from market_models import MarketSnapshot
from src.storage.sqlite_store import SqliteStore


def _snap(goods_id: str = "42552") -> MarketSnapshot:
    return MarketSnapshot(
        goods_id=goods_id,
        family="Karambit",
        skin_name="Karambit | Doppler (Factory New)",
        condition="Factory New",
        price=100.0,
        listings=5,
        buy_orders=2,
        reference_price=120.0,
        image_url="",
        observed_orders=0,
    )


def test_sqlite_store_roundtrip(tmp_path):
    db = str(tmp_path / "test.sqlite3")
    store = SqliteStore(db)
    store.write_snapshots([_snap()], "2024-01-01 00:00:00")
    df = store.load_history_frame()
    assert not df.empty
    assert list(df.columns) == HISTORY_HEADERS
    assert df.iloc[0]["Goods ID"] == "42552"


def test_sqlite_store_empty_file_returns_empty_frame(tmp_path):
    db = str(tmp_path / "nonexistent.sqlite3")
    store = SqliteStore(db)
    df = store.load_history_frame()
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_sqlite_store_duplicate_upsert_safe(tmp_path):
    db = str(tmp_path / "test.sqlite3")
    store = SqliteStore(db)
    snap = _snap()
    store.write_snapshots([snap], "2024-01-01 00:00:00")
    store.write_snapshots([snap], "2024-01-01 00:00:00")
    df = store.load_history_frame()
    assert len(df) == 1
