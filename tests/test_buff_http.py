from __future__ import annotations

from src.buff_http import buff_headers, max_429_attempts, request_timeout


def test_buff_headers_add_cookie_and_csrf(monkeypatch):
    monkeypatch.setenv("BUFF_COOKIE", "csrf_token=abc123; session=xyz")

    headers = buff_headers()

    assert headers["Cookie"] == "csrf_token=abc123; session=xyz"
    assert headers["X-CSRFToken"] == "abc123"


def test_request_timeout_reads_env(monkeypatch):
    monkeypatch.setenv("BUFF_REQUEST_TIMEOUT", "7")
    assert request_timeout() == 7


def test_max_429_attempts_has_minimum_one(monkeypatch):
    monkeypatch.setenv("BUFF_MAX_429_ATTEMPTS", "0")
    assert max_429_attempts() == 1
