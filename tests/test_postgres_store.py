from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from market_config import HISTORY_HEADERS
from market_models import MarketSnapshot


def _make_snapshot(goods_id: str = "42552", price: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(
        goods_id=goods_id,
        family="Karambit",
        skin_name="Karambit | Doppler (Factory New)",
        condition="Factory New",
        price=price,
        listings=10,
        buy_orders=5,
        reference_price=120.0,
        image_url="https://example.com/img.png",
        observed_orders=2,
    )


@pytest.fixture()
def _mock_transaction(monkeypatch):
    """Patch src.db.postgres_client.transaction to a mock cursor."""
    from contextlib import contextmanager

    mock_cursor = MagicMock()
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("BUFF_AUTO_MIGRATE_POSTGRES", "0")

    @contextmanager
    def fake_transaction():
        yield mock_cursor

    monkeypatch.setattr("src.storage.postgres_store.transaction", fake_transaction)
    return mock_cursor


def test_write_snapshots_executes_upserts(_mock_transaction):
    from src.storage.postgres_store import PostgresStore

    store = PostgresStore()
    snap = _make_snapshot()
    store.write_snapshots([snap], "2024-01-01 00:00:00")

    assert _mock_transaction.execute.call_count == 2
    calls = _mock_transaction.execute.call_args_list
    # First call inserts into goods
    assert "goods" in calls[0][0][0]
    assert snap.goods_id in calls[0][0][1]
    # Second call inserts into snapshots
    assert "snapshots" in calls[1][0][0]
    assert snap.price in calls[1][0][1]


def test_write_snapshots_empty_does_nothing(_mock_transaction):
    from src.storage.postgres_store import PostgresStore

    store = PostgresStore()
    store.write_snapshots([], "2024-01-01 00:00:00")
    _mock_transaction.execute.assert_not_called()


def test_load_history_frame_empty_returns_empty_dataframe(_mock_transaction):
    from src.storage.postgres_store import PostgresStore

    _mock_transaction.fetchall.return_value = []
    store = PostgresStore()
    df = store.load_history_frame()
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert list(df.columns) == HISTORY_HEADERS


def test_load_history_frame_returns_history_shaped_dataframe(_mock_transaction):
    from src.storage.postgres_store import PostgresStore

    _mock_transaction.fetchall.return_value = [
        {
            "Timestamp": "2024-01-01 00:00:00",
            "Goods ID": "42552",
            "Family": "Karambit",
            "Knife Type": "Karambit",
            "Skin Name": "Karambit | Doppler (Factory New)",
            "Condition": "Factory New",
            "Price": 100.0,
            "Listings": 10,
            "Buy Orders": 5,
            "Reference Price": 120.0,
            "Image URL": "https://example.com/img.png",
            "Observed Orders": 2,
        }
    ]
    store = PostgresStore()
    df = store.load_history_frame()
    assert not df.empty
    assert list(df.columns) == HISTORY_HEADERS
    assert df.iloc[0]["Goods ID"] == "42552"


def test_load_history_frame_db_error_returns_empty(_mock_transaction):
    from src.storage.postgres_store import PostgresStore

    _mock_transaction.execute.side_effect = Exception("connection refused")
    store = PostgresStore()
    df = store.load_history_frame()
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_write_snapshots_uses_parameterized_sql(_mock_transaction):
    """Verify no string formatting — all values passed as parameters."""
    from src.storage.postgres_store import PostgresStore

    store = PostgresStore()
    snap = _make_snapshot(goods_id="99999", price=999.99)
    store.write_snapshots([snap], "2024-06-01 12:00:00")

    for call in _mock_transaction.execute.call_args_list:
        sql_template = call[0][0]
        # The SQL must contain %s placeholders, not the actual values
        assert "99999" not in sql_template
        assert "999.99" not in sql_template
        assert "%s" in sql_template
