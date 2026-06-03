from __future__ import annotations

from src.retry import (
    backoff_base_seconds,
    compute_backoff,
    is_retryable_status,
    max_retries,
)


def test_retryable_statuses():
    for code in (429, 500, 502, 503, 504):
        assert is_retryable_status(code)
    for code in (200, 301, 400, 401, 403, 404):
        assert not is_retryable_status(code)


def test_max_retries_reads_env(monkeypatch):
    monkeypatch.setenv("BUFF_MAX_RETRIES", "5")
    assert max_retries() == 5


def test_max_retries_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("BUFF_MAX_RETRIES", "not-a-number")
    assert max_retries(default=2) == 2


def test_max_retries_negative_clamped(monkeypatch):
    monkeypatch.setenv("BUFF_MAX_RETRIES", "-1")
    assert max_retries() == 0


def test_backoff_base_reads_env(monkeypatch):
    monkeypatch.setenv("BUFF_BACKOFF_BASE_SECONDS", "2.5")
    assert backoff_base_seconds() == 2.5


def test_compute_backoff_no_jitter_is_exponential():
    assert compute_backoff(0, 1.0, jitter=False) == 1.0
    assert compute_backoff(1, 1.0, jitter=False) == 2.0
    assert compute_backoff(2, 1.0, jitter=False) == 4.0


def test_compute_backoff_capped():
    assert compute_backoff(10, 1.0, jitter=False, cap=8.0) == 8.0


def test_compute_backoff_jitter_within_bounds():
    for _ in range(100):
        delay = compute_backoff(2, 1.0, cap=8.0)
        assert 0.0 <= delay <= 4.0
