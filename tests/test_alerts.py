from __future__ import annotations

from unittest.mock import patch

from src.alerts import AlertDispatcher


def test_send_buy_watch_calls_post(monkeypatch):
    monkeypatch.setenv("ALERT_DISCORD_WEBHOOK", "https://discord.example/webhook")
    d = AlertDispatcher()
    row = {
        "signal": "BUY_WATCH",
        "skin_name": "Karambit",
        "latest_price": 100,
        "average_price": 105,
        "latest_listings": 10,
        "price_change_pct": -3.2,
        "confidence": 0.8,
        "rationale": "test",
    }
    with patch("src.alerts.requests.post") as post:
        d.send(row)
        assert post.called


def test_send_hold_skips(monkeypatch):
    monkeypatch.setenv("ALERT_DISCORD_WEBHOOK", "https://discord.example/webhook")
    d = AlertDispatcher()
    with patch("src.alerts.requests.post") as post:
        d.send({"signal": "HOLD"})
        assert not post.called
