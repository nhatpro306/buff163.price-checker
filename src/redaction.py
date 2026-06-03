"""Redaction helpers so secrets never reach logs or returned payloads.

Used by the Lambda handler and safe for any log path. Redacts:
- values of known secret env vars (exact match),
- credentials embedded in URLs (``scheme://user:pass@host`` → masked),
- Discord webhook URLs.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable

REDACTED = "***"

# Env vars whose values must never appear in output.
SECRET_ENV_KEYS = (
    "DATABASE_URL",
    "BUFF_COOKIE",
    "GSHEET_CREDS_JSON",
    "GSHEET_CREDS",
    "GOOGLE_CREDENTIALS_JSON",
    "GOOGLE_APPLICATION_CREDENTIALS_JSON",
    "DISCORD_WEBHOOK_URL",
)

# scheme://user:pass@host -> scheme://***:***@host
_URL_CRED_RE = re.compile(r"(?P<scheme>[a-zA-Z][\w+.-]*://)[^/\s:@]+:[^/\s:@]+@")
# Discord webhook URLs.
_DISCORD_RE = re.compile(r"https://discord(?:app)?\.com/api/webhooks/\S+")


def redact_secrets(text: str, *, extra_values: Iterable[str] = ()) -> str:
    """Return ``text`` with known secret material masked."""
    if not text:
        return text
    out = text
    for key in SECRET_ENV_KEYS:
        value = os.getenv(key)
        if value and value in out:
            out = out.replace(value, REDACTED)
    for value in extra_values:
        if value and value in out:
            out = out.replace(value, REDACTED)
    out = _URL_CRED_RE.sub(rf"\g<scheme>{REDACTED}:{REDACTED}@", out)
    out = _DISCORD_RE.sub(REDACTED, out)
    return out


def redact_value(value: str | None) -> str:
    """Mask a single secret value entirely."""
    return REDACTED if value else ""


__all__ = ["REDACTED", "SECRET_ENV_KEYS", "redact_secrets", "redact_value"]
