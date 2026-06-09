"""Optional real listing-count enrichment from the BUFF163 goods API.

The free-tier dashboard's price data comes from the cookieless csgotrader feed,
which has no order-book depth. BUFF's own goods-list endpoint returns ``sell_num``
(the "Sell(N)" listing count shown on each goods page) together with the numeric
``goods_id`` and ``market_hash_name`` — so a few paginated calls cover the most
actively listed knives in one shot, instead of one request per item.

This requires a valid BUFF session cookie (the user's own), stored in SSM as a
SecureString. When no cookie is configured the whole step is skipped and the
dashboard stays price-only — nothing here ever fails the build.

Uses urllib only (no extra Lambda zip dependency). Never logs the cookie.
"""
from __future__ import annotations

import gzip
import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any

LOG = logging.getLogger(__name__)

GOODS_LIST_URL = "https://buff.163.com/api/market/goods"
PRICE_HISTORY_URL = "https://buff.163.com/api/market/goods/price_history/buff"


def _normalize_name(name: str) -> str:
    """Match key: drop the ★ star and collapse whitespace, keep StatTrak/wear."""
    return " ".join(str(name).replace("★", "").split()).strip().lower()


def _get_json(url: str, cookie: str, timeout: int) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip",
            "User-Agent": "Mozilla/5.0 (compatible; buff163-free-tier/1.0)",
            "Referer": "https://buff.163.com/market/csgo",
            "Cookie": cookie,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        body = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            body = gzip.decompress(body)
        return json.loads(body.decode("utf-8"))


def fetch_listing_map(
    cookie: str,
    *,
    pages: int = 4,
    page_size: int = 50,
    sleep_seconds: float = 1.5,
    timeout: int = 15,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Return ({normalized_name: {goods_id, listing_count, sell_min_price}}, errors).

    Pages the knife goods list sorted by listing count (sell_num desc), so the
    most actively listed items come first. Stops early on any non-OK response.
    Never raises.
    """
    if not cookie:
        return {}, ["buff_cookie_absent"]

    out: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for page in range(1, max(1, pages) + 1):
        params = urllib.parse.urlencode(
            {
                "game": "csgo",
                "category_group": "knife",
                "page_num": page,
                "page_size": page_size,
                "sort_by": "sell_num.desc",
            }
        )
        url = f"{GOODS_LIST_URL}?{params}"
        try:
            payload = _get_json(url, cookie, timeout)
        except Exception as exc:  # noqa: BLE001 - boundary
            errors.append(f"buff_fetch_failed_page{page}: {type(exc).__name__}")
            break

        if payload.get("code") != "OK":
            # e.g. "Login Required" when the cookie is invalid/expired.
            errors.append(f"buff_api_code_page{page}: {payload.get('code')}")
            break

        items = ((payload.get("data") or {}).get("items")) or []
        if not items:
            break
        for item in items:
            name = item.get("market_hash_name") or ""
            goods_id = item.get("id")
            sell_num = item.get("sell_num")
            if not name or goods_id is None:
                continue
            key = _normalize_name(name)
            try:
                listing = int(sell_num)
            except (TypeError, ValueError):
                continue
            out[key] = {
                "goods_id": int(goods_id),
                "listing_count": listing,
                "sell_min_price": item.get("sell_min_price"),
            }
        if page < pages:
            time.sleep(sleep_seconds)

    return out, errors


def fetch_price_history(
    cookie: str,
    goods_id: int,
    *,
    days: int = 365,
    usd_to_cny: float = 1.0,
    timeout: int = 15,
) -> list[list[float]]:
    """Return [[epoch_ms, price_cny], ...] for one goods_id, or [] on failure.

    BUFF's price_history endpoint returns prices already in the requested
    currency (CNY here), so usd_to_cny defaults to 1. Never raises.
    """
    params = urllib.parse.urlencode(
        {
            "game": "csgo",
            "goods_id": goods_id,
            "currency": "CNY",
            "days": days,
            "buff_price_type": 2,
        }
    )
    try:
        payload = _get_json(f"{PRICE_HISTORY_URL}?{params}", cookie, timeout)
    except Exception:  # noqa: BLE001 - boundary
        return []
    if payload.get("code") != "OK":
        return []
    raw = ((payload.get("data") or {}).get("price_history")) or []
    points: list[list[float]] = []
    for entry in raw:
        try:
            ts = float(entry[0])
            price = float(entry[1]) * usd_to_cny
        except (TypeError, ValueError, IndexError):
            continue
        points.append([round(ts), round(price, 2)])
    return points


def build_price_history(
    cookie: str,
    goods_ids: list[int],
    *,
    days: int = 365,
    sleep_seconds: float = 1.2,
    timeout: int = 15,
) -> dict[str, list[list[float]]]:
    """Fetch price history for several goods_ids. Keyed by str(goods_id)."""
    out: dict[str, list[list[float]]] = {}
    for i, gid in enumerate(goods_ids):
        pts = fetch_price_history(cookie, gid, days=days, timeout=timeout)
        if pts:
            out[str(gid)] = pts
        if i + 1 < len(goods_ids):
            time.sleep(sleep_seconds)
    return out


def enrich_rows(
    rows: list[dict[str, Any]], listing_map: dict[str, dict[str, Any]]
) -> int:
    """Set listing_count + buff_url on rows that match the BUFF listing map.

    Matches on the normalized market_hash_name. Returns the number of rows
    enriched. Rows with no match keep listing_count = None (unknown).
    """
    enriched = 0
    for row in rows:
        key = _normalize_name(row.get("market_hash_name") or "")
        hit = listing_map.get(key)
        if not hit:
            continue
        row["listing_count"] = hit["listing_count"]
        gid = hit.get("goods_id")
        if gid is not None:
            row["buff_url"] = f"https://buff.163.com/goods/{gid}"
        enriched += 1
    return enriched
