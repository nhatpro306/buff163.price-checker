from __future__ import annotations

from unittest.mock import patch

import handler
from src.results import ScrapeRunSummary


def _summary(succeeded=2, failed=0, skipped=0):
    s = ScrapeRunSummary(
        started_at="2026-06-03 00:00:00",
        finished_at="2026-06-03 00:00:10",
        attempted=succeeded + failed + skipped,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
    )
    s.finalize()
    return s


def test_lambda_handler_success():
    with patch("handler.run", return_value=_summary(succeeded=3)):
        out = handler.lambda_handler({}, None)
    assert out["ok"] is True
    assert out["status"] == "success"
    assert out["attempted"] == 3
    assert out["succeeded"] == 3
    assert "duration_seconds" in out


def test_lambda_handler_all_failed_not_ok():
    with patch("handler.run", return_value=_summary(succeeded=0, failed=3)):
        out = handler.lambda_handler({}, None)
    assert out["ok"] is False
    assert out["status"] == "failed"


def test_lambda_handler_exception_returns_safe_result():
    with patch("handler.run", side_effect=RuntimeError("boom")):
        out = handler.lambda_handler({}, None)
    assert out["ok"] is False
    assert out["status"] == "failed"
    assert out["error_type"] == "RuntimeError"
    assert out["error_message"] == "boom"


def test_lambda_handler_migration_path():
    with patch("handler.run", return_value=None):
        out = handler.lambda_handler({}, None)
    assert out["ok"] is True
    assert out["status"] == "success"


def test_lambda_handler_scrubs_secret_in_error(monkeypatch):
    secret = "postgresql://user:p%40ss@db.example.com:5432/buff"
    monkeypatch.setenv("DATABASE_URL", secret)
    with patch("handler.run", side_effect=RuntimeError(f"connect failed dsn={secret}")):
        out = handler.lambda_handler({}, None)
    assert secret not in out["error_message"]
    assert "***" in out["error_message"]


def test_lambda_handler_no_secret_keys_in_output():
    # Returned dict must never contain raw secret env var values.
    with patch("handler.run", return_value=_summary(succeeded=1)):
        out = handler.lambda_handler({}, None)
    blob = str(out).lower()
    for leaked in ("password", "cookie", "database_url", "webhook"):
        assert leaked not in blob


def test_lambda_handler_health_check_mode():
    with patch("handler.run_health_check", return_value={"ok": True, "status": "healthy"}) as hc:
        with patch("handler.run", side_effect=AssertionError("must not scrape")):
            out = handler.lambda_handler({"mode": "health_check"}, None)
    assert out == {"ok": True, "status": "healthy"}
    hc.assert_called_once()


def test_lambda_handler_summary_includes_backend():
    s = _summary(succeeded=2)
    s.storage_backend = "postgres"
    with patch("handler.run", return_value=s):
        out = handler.lambda_handler({}, None)
    assert out["storage_backend"] == "postgres"
    assert out["invalid"] == out["skipped"]


def test_ensure_writable_paths_only_in_lambda(monkeypatch):
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.delenv("BUFF_SQLITE_PATH", raising=False)
    handler._ensure_writable_paths()
    assert "BUFF_SQLITE_PATH" not in __import__("os").environ

    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "buff-scraper")
    monkeypatch.delenv("BUFF_SQLITE_PATH", raising=False)
    handler._ensure_writable_paths()
    assert __import__("os").environ["BUFF_SQLITE_PATH"] == "/tmp/buff163.sqlite3"
