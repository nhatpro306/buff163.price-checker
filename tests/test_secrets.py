from __future__ import annotations

import pytest

from src import secrets


def test_get_secret_prefers_direct_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("DATABASE_URL_SECRET_ARN", "arn:should-not-be-used")
    # Direct env wins; Secrets Manager must not be called.
    monkeypatch.setattr(
        secrets, "_fetch_from_secrets_manager", lambda arn: pytest.fail("should not fetch")
    )
    assert secrets.get_secret("DATABASE_URL") == "postgresql://x"


def test_get_secret_uses_arn_when_no_env(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL_SECRET_ARN", "arn:aws:secretsmanager:...:DATABASE_URL")
    monkeypatch.setattr(secrets, "_fetch_from_secrets_manager", lambda arn: "postgresql://fetched")
    assert secrets.get_secret("DATABASE_URL") == "postgresql://fetched"
    # Hydrated into env for downstream getenv callers.
    import os

    assert os.environ["DATABASE_URL"] == "postgresql://fetched"


def test_get_secret_returns_default_when_missing(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    monkeypatch.delenv("NOPE_SECRET_ARN", raising=False)
    assert secrets.get_secret("NOPE", default="fallback") == "fallback"


def test_require_secret_raises_when_missing(monkeypatch):
    monkeypatch.delenv("MISSING", raising=False)
    monkeypatch.delenv("MISSING_SECRET_ARN", raising=False)
    with pytest.raises(RuntimeError):
        secrets.require_secret("MISSING")


def test_hydrate_secrets_reports_resolved(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.delenv("BUFF_COOKIE", raising=False)
    monkeypatch.delenv("BUFF_COOKIE_SECRET_ARN", raising=False)
    resolved = secrets.hydrate_secrets(("DATABASE_URL", "BUFF_COOKIE"))
    assert resolved == ["DATABASE_URL"]
