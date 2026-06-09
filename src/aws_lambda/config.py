"""Lambda configuration loader for the free-tier scraper.

All values come from environment variables. No defaults that could leak
secrets. Sensitive values are loaded from SSM Parameter Store at call time and
never logged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _list(name: str) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass(frozen=True)
class Config:
    s3_bucket: str
    region: str
    log_level: str
    request_timeout_s: int
    max_retries: int
    price_drop_alert_percent: float
    write_sheets: bool
    spreadsheet_id: str
    worksheet_name: str
    google_creds_ssm_param: str
    discord_webhook_ssm_param: str
    scraper_targets: list[str]
    history_keep_days: int
    raw_keep_days: int


def load_config() -> Config:
    """Read environment into a typed Config. No secrets are read here."""
    return Config(
        s3_bucket=os.getenv("S3_BUCKET", "").strip(),
        region=os.getenv("AWS_REGION", "ap-northeast-1").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        request_timeout_s=_int("REQUEST_TIMEOUT_SECONDS", 15),
        max_retries=_int("MAX_RETRIES", 3),
        price_drop_alert_percent=_float("PRICE_DROP_ALERT_PERCENT", 0.0),
        write_sheets=_bool("WRITE_SHEETS", False),
        spreadsheet_id=os.getenv("SPREADSHEET_ID", "").strip(),
        worksheet_name=os.getenv("WORKSHEET_NAME", "").strip(),
        google_creds_ssm_param=os.getenv(
            "GOOGLE_CREDS_SSM_PARAM", "/buff163/google-creds"
        ).strip(),
        discord_webhook_ssm_param=os.getenv(
            "DISCORD_WEBHOOK_SSM_PARAM", "/buff163/discord-webhook"
        ).strip(),
        scraper_targets=_list("SCRAPER_TARGETS"),
        history_keep_days=_int("HISTORY_KEEP_DAYS", 90),
        raw_keep_days=_int("RAW_KEEP_DAYS", 14),
    )
