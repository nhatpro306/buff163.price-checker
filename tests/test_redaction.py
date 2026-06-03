from __future__ import annotations

from src.redaction import REDACTED, redact_secrets, redact_value


def test_redacts_database_url_credentials():
    text = "could not connect to postgresql://admin:s3cr3t@db.host:5432/buff"
    out = redact_secrets(text)
    assert "s3cr3t" not in out
    assert "admin" not in out
    assert "postgresql://***:***@db.host:5432/buff" in out


def test_redacts_discord_webhook():
    text = "posting to https://discord.com/api/webhooks/123/abcDEF then done"
    out = redact_secrets(text)
    assert "abcDEF" not in out
    assert REDACTED in out


def test_redacts_known_env_value(monkeypatch):
    monkeypatch.setenv("BUFF_COOKIE", "session=supersecretcookie")
    out = redact_secrets("request failed with cookie session=supersecretcookie")
    assert "supersecretcookie" not in out
    assert REDACTED in out


def test_redacts_extra_values():
    out = redact_secrets("token=abc123xyz", extra_values=["abc123xyz"])
    assert "abc123xyz" not in out


def test_empty_text_is_safe():
    assert redact_secrets("") == ""


def test_redact_value():
    assert redact_value("anything") == REDACTED
    assert redact_value(None) == ""
    assert redact_value("") == ""
