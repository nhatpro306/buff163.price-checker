"""Discord failure alert for the free-tier Lambda.

One POST per Lambda run, only on failure or partial success. Never logs the
webhook URL. Uses urllib so no extra dependency.
"""
from __future__ import annotations

import json
import logging
import urllib.request

LOG = logging.getLogger(__name__)


def send_discord_alert(webhook_url: str, status: str, summary: dict) -> bool:
    """Send a single short Discord message. Returns True on success.

    Never raises. Never logs the webhook URL or full payload.
    """
    if not webhook_url:
        return False

    items_scraped = int(summary.get("items_scraped") or 0)
    items_saved = int(summary.get("items_saved") or 0)
    errors = summary.get("errors") or []
    error_count = len(errors) if isinstance(errors, list) else 0
    first_error = ""
    if error_count:
        first_error = str(errors[0])[:200]

    content = (
        f":warning: **BUFF163 scraper {status}**\n"
        f"timestamp: `{summary.get('timestamp', '?')}`\n"
        f"scraped: {items_scraped} | saved: {items_saved} | errors: {error_count}\n"
        + (f"first_error: `{first_error}`" if first_error else "")
    )

    body = json.dumps({"content": content}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            response.read()
        LOG.info("discord_alert_sent status=%s", status)
        return True
    except Exception as exc:  # noqa: BLE001 - alerts must never crash Lambda
        LOG.warning("discord_alert_failed type=%s", type(exc).__name__)
        return False
