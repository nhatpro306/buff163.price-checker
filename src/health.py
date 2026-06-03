"""Health-check mode for scheduled cloud runs.

Verifies config and storage wiring WITHOUT scraping real data, so an operator
can confirm a deployment is healthy before/independently of a real run.
Never logs or returns secret values.
"""

from __future__ import annotations

import os
from typing import Any

from src.redaction import redact_secrets
from src.secrets import get_secret


def run_health_check() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    ok = True

    backend = os.getenv("STORAGE_BACKEND", "sheets").strip().lower()
    checks["storage_backend"] = backend

    # Required config present (resolves env or Secrets Manager ARN, value not stored).
    if backend == "postgres":
        has_db = get_secret("DATABASE_URL") is not None
        checks["database_url_present"] = has_db
        ok = ok and has_db

    # Storage backend constructs without error (connectivity/credentials probe).
    try:
        from src.storage.factory import get_storage_backend  # noqa: PLC0415

        get_storage_backend()
        checks["storage_init"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        checks["storage_init"] = "error"
        checks["storage_error"] = redact_secrets(str(exc))[:200]
        ok = False

    return {
        "ok": ok,
        "status": "healthy" if ok else "unhealthy",
        "mode": "health_check",
        "checks": checks,
    }


__all__ = ["run_health_check"]
