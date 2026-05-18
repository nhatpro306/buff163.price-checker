from __future__ import annotations

import os
from http.cookies import SimpleCookie


def buff_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://buff.163.com/market/csgo",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    cookie = os.getenv("BUFF_COOKIE")
    if cookie:
        headers["Cookie"] = cookie
        csrf_token = _csrf_token_from_cookie(cookie)
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token
    return headers


def request_timeout(default: int = 20) -> int:
    return int(os.getenv("BUFF_REQUEST_TIMEOUT", str(default)))


def max_429_attempts(default: int = 5) -> int:
    return max(1, int(os.getenv("BUFF_MAX_429_ATTEMPTS", str(default))))


def _csrf_token_from_cookie(cookie: str) -> str | None:
    parsed_cookie = SimpleCookie()
    try:
        parsed_cookie.load(cookie)
        csrf_token = parsed_cookie.get("csrf_token")
    except Exception:
        return None
    return csrf_token.value if csrf_token else None
