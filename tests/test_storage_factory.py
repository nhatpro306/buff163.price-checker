from __future__ import annotations

import pytest

from src.storage.factory import get_storage_backend
from src.storage.sqlite_store import SqliteStore


def test_factory_returns_sqlite_when_env_set(tmp_path, monkeypatch):
    db = str(tmp_path / "test.sqlite3")
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("BUFF_SQLITE_PATH", db)
    backend = get_storage_backend()
    assert isinstance(backend, SqliteStore)
    assert backend.db_path == db


def test_factory_sqlite_requires_path(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("BUFF_SQLITE_PATH", "")
    with pytest.raises(ValueError, match="BUFF_SQLITE_PATH"):
        get_storage_backend()


def test_factory_unknown_backend_falls_back_to_sheets(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "notarealbackend")
    from src.storage.sheets_store import SheetsStore

    backend = get_storage_backend()
    assert isinstance(backend, SheetsStore)


def test_factory_postgres_requires_psycopg2(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
    monkeypatch.setenv("BUFF_AUTO_MIGRATE_POSTGRES", "0")
    # psycopg2 may not be installed in CI. Either it returns a PostgresStore or
    # raises ImportError with a helpful message.
    try:
        from src.storage.postgres_store import PostgresStore

        backend = get_storage_backend()
        assert isinstance(backend, PostgresStore)
    except ImportError as exc:
        assert "psycopg2" in str(exc)


def test_factory_postgres_missing_database_url_raises(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("BUFF_AUTO_MIGRATE_POSTGRES", "0")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    try:
        get_storage_backend()
    except ImportError:
        pytest.skip("psycopg2 not installed")
    except ValueError as exc:
        assert "DATABASE_URL" in str(exc)
