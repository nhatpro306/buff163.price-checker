"""AWS Lambda entrypoint for the BUFF163 scraper.

The same scrape logic runs locally (`python main.py`) and in Lambda (this
handler). The handler is a thin wrapper around `src.orchestrator.run()`:
it returns a JSON-serializable run summary and never returns or logs secrets.

Local CLI behaviour is unchanged — this module only adds an additional entry
point and is not imported by the CLI path.
"""

from __future__ import annotations

import os
from typing import Any

from src.health import run_health_check
from src.orchestrator import run
from src.redaction import redact_secrets
from src.results import ScrapeRunSummary
from src.secrets import hydrate_secrets

# Secrets resolved (env or Secrets Manager ARN) before a run so downstream
# os.getenv() callers see them.
_HYDRATE = ("DATABASE_URL", "BUFF_COOKIE")


def _running_in_lambda() -> bool:
    return bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


def _ensure_writable_paths() -> None:
    """Lambda only allows writes under /tmp. Redirect file-based defaults there
    so a stray local-file write cannot crash an otherwise cloud-safe run."""
    if _running_in_lambda():
        os.environ.setdefault("BUFF_SQLITE_PATH", "/tmp/buff163.sqlite3")
        os.environ.setdefault("BUFF_PAGE_META_CACHE_PATH", "/tmp/page_meta_cache.sqlite3")


def _summary_to_dict(summary: ScrapeRunSummary) -> dict[str, Any]:
    body = summary.to_dict()
    body["ok"] = summary.exit_code() == 0
    return body


def lambda_handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, Any]:
    """Run one scrape and return a JSON-serializable summary.

    Never raises: fatal errors are reported as a structured result with
    ``ok=False`` so EventBridge/CloudWatch see a clear, secret-free message.
    """
    _ensure_writable_paths()
    # Pull DATABASE_URL / BUFF_COOKIE from Secrets Manager if only ARNs are set.
    hydrate_secrets(_HYDRATE)

    # Health-check mode: verify config/storage without scraping.
    event = event or {}
    if event.get("mode") == "health_check" or os.getenv("BUFF_HEALTH_CHECK") == "1":
        return run_health_check()

    try:
        summary = run()
    except Exception as exc:  # noqa: BLE001 - boundary: convert to safe result
        return {
            "ok": False,
            "status": "failed",
            "error_type": exc.__class__.__name__,
            "error_message": redact_secrets(str(exc))[:300],
        }

    if summary is None:
        # Migration-only / no-scrape path returns no summary object.
        return {"ok": True, "status": "success", "detail": "no scrape summary (migration path)"}

    return _summary_to_dict(summary)


__all__ = ["lambda_handler"]
