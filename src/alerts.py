from __future__ import annotations

import os

import requests


class AlertDispatcher:
    def __init__(self):
        self.discord_url = os.getenv("ALERT_DISCORD_WEBHOOK")
        self.telegram_token = os.getenv("ALERT_TELEGRAM_TOKEN")
        self.telegram_chat_id = os.getenv("ALERT_TELEGRAM_CHAT_ID")

    def should_send(self, signal: str) -> bool:
        return signal in {"BUY_WATCH", "SELL_WATCH", "ACCUMULATE", "TAKE_PROFIT"}

    def send(self, summary: dict) -> None:
        if not self.should_send(summary.get("signal", "")):
            return
        message = self._format(summary)
        if self.discord_url:
            self._send_discord(message)
        if self.telegram_token and self.telegram_chat_id:
            self._send_telegram(message)

    def _format(self, s: dict) -> str:
        emoji = {
            "BUY_WATCH": "??",
            "SELL_WATCH": "??",
            "ACCUMULATE": "??",
            "TAKE_PROFIT": "??",
        }.get(s["signal"], "?")
        return (
            f"{emoji} **{s['signal']}** - {s['skin_name']}\n"
            f"Price: ?{s['latest_price']} (avg ?{s['average_price']})\n"
            f"Listings: {s['latest_listings']} | Change: {s['price_change_pct']:+.1f}%\n"
            f"Confidence: {s['confidence']:.0%} | {s['rationale']}"
        )

    def _send_discord(self, message: str) -> None:
        if not self.discord_url:
            return
        requests.post(self.discord_url, json={"content": message}, timeout=10)

    def _send_telegram(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        requests.post(
            url,
            json={
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )


__all__ = ["AlertDispatcher"]
