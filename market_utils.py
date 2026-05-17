from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

from market_config import CSGO_API_SKINS_URL

QUALITY_MAP = {
    "崭新出厂": "Factory New",
    "略有磨损": "Minimal Wear",
    "久经沙场": "Field-Tested",
    "破损不堪": "Well-Worn",
    "战痕累累": "Battle-Scarred",
    "★ StatTrak™": "StatTrak",
    "StatTrak™": "StatTrak",
}


def try_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def normalize_image_url(value: Any) -> str:
    url = str(value or "").strip()
    if url.startswith("//"):
        return f"https:{url}"
    return url


def source_id(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha1(value.encode('utf-8')).hexdigest()[:16]}"


def load_json_file(path: str) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json_file(path: str, data: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def steam_image_url(market_hash_name: str, cache: dict[str, Any]) -> str:
    if market_hash_name in cache:
        return str(cache[market_hash_name] or "")
    query = market_hash_name.strip()
    if not query.startswith("★") and (
        "Knife" in query or "Karambit" in query or "Bayonet" in query
    ):
        query = f"★ {query}"
    params: dict[str, str | int] = {
        "query": query,
        "start": 0,
        "count": 1,
        "search_descriptions": 0,
        "sort_column": "popular",
        "sort_dir": "desc",
        "appid": 730,
        "norender": 1,
    }
    response = requests.get(
        "https://steamcommunity.com/market/search/render/",
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    icon_url = (
        ((results[0] if results else {}).get("asset_description") or {}).get("icon_url") or ""
    ).strip()
    url = f"https://community.fastly.steamstatic.com/economy/image/{icon_url}" if icon_url else ""
    cache[market_hash_name] = url
    time.sleep(float(os.getenv("STEAM_IMAGE_DELAY", "0.25")))
    return url


def csgo_api_image_map() -> dict[str, str]:
    response = requests.get(CSGO_API_SKINS_URL, timeout=30)
    response.raise_for_status()
    images: dict[str, str] = {}
    for item in response.json():
        name = str(item.get("name") or "").replace("★ ", "").strip()
        image = str(item.get("image") or "").strip()
        if not name or not image:
            continue
        images[name] = image
        images[f"StatTrak™ {name}"] = image
        for wear in item.get("wears") or []:
            wear_name = str((wear or {}).get("name") or "").strip()
            if wear_name:
                images[f"{name} ({wear_name})"] = image
                images[f"StatTrak™ {name} ({wear_name})"] = image
    return images


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def split_market_name(name: str) -> tuple[str, str]:
    cleaned = name.replace("★ ", "").strip()
    match = re.match(r"(.+?) \((.+)\)$", cleaned)
    if not match:
        return cleaned, ""
    return match.group(1).strip(), match.group(2).strip()


def canonicalize_family_name(name: str) -> str:
    value = (name or "").strip().replace("★ ", "")
    if value.startswith("Butterfly | "):
        return value.replace("Butterfly | ", "Butterfly Knife | ", 1)
    if value.startswith("StatTrak™ Butterfly | "):
        return value.replace("StatTrak™ Butterfly | ", "StatTrak™ Butterfly Knife | ", 1)
    return value


def clean_html_text(raw_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    for cn, en in QUALITY_MAP.items():
        text = text.replace(cn, en)
    return text
