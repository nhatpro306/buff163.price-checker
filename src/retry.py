"""HTTP retry helpers: error classification + exponential backoff with jitter.

Design borrowed (concepts only, no vendored code) from Tenacity and Scrapy's
RetryMiddleware: retry only transient failures, cap attempts, add jitter so
concurrent scheduled runs do not synchronize their retries. See
docs/scraper-reference-patterns.md.
"""

from __future__ import annotations

import os
import random

# Transient HTTP statuses worth retrying. 4xx client errors (403/404) are NOT
# here on purpose: retrying them wastes time and can look like abuse.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_CAP_SECONDS = 8.0


def max_retries(default: int = DEFAULT_MAX_RETRIES) -> int:
    """Extra attempts after the first try. ``BUFF_MAX_RETRIES`` overrides."""
    try:
        return max(0, int(os.getenv("BUFF_MAX_RETRIES", str(default))))
    except ValueError:
        return default


def backoff_base_seconds(default: float = DEFAULT_BACKOFF_BASE_SECONDS) -> float:
    """Base delay for exponential backoff. ``BUFF_BACKOFF_BASE_SECONDS`` overrides."""
    try:
        return max(0.0, float(os.getenv("BUFF_BACKOFF_BASE_SECONDS", str(default))))
    except ValueError:
        return default


def is_retryable_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS_CODES


def compute_backoff(
    attempt: int,
    base: float,
    *,
    cap: float = _BACKOFF_CAP_SECONDS,
    jitter: bool = True,
) -> float:
    """Full-jitter exponential backoff: random delay in ``[0, min(cap, base*2**attempt)]``."""
    ceiling = min(cap, base * (2**attempt))
    if ceiling <= 0:
        return 0.0
    if jitter:
        return random.uniform(0.0, ceiling)
    return ceiling


__all__ = [
    "RETRYABLE_STATUS_CODES",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_BACKOFF_BASE_SECONDS",
    "max_retries",
    "backoff_base_seconds",
    "is_retryable_status",
    "compute_backoff",
]
