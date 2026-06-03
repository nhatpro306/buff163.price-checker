from __future__ import annotations

from unittest.mock import patch

from src import health


def test_health_ok_when_storage_inits(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")
    with patch("src.storage.factory.get_storage_backend", return_value=object()):
        out = health.run_health_check()
    assert out["ok"] is True
    assert out["status"] == "healthy"
    assert out["checks"]["storage_backend"] == "sqlite"


def test_health_unhealthy_when_storage_fails(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    with patch(
        "src.storage.factory.get_storage_backend",
        side_effect=RuntimeError("connect to postgresql://u:p@h/db failed"),
    ):
        out = health.run_health_check()
    assert out["ok"] is False
    assert out["status"] == "unhealthy"
    # Error message must be redacted (no raw credentials).
    assert "u:p@h" not in str(out)


def test_health_postgres_missing_database_url(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_SECRET_ARN", raising=False)
    with patch("src.storage.factory.get_storage_backend", return_value=object()):
        out = health.run_health_check()
    assert out["checks"]["database_url_present"] is False
    assert out["ok"] is False
