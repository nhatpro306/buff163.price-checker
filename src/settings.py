from __future__ import annotations

import os

from market_config import DEFAULT_KNIFE_CATEGORIES, DEFAULT_KNIFE_FINISHES
from market_utils import env_flag


def get_seed_goods_ids() -> list[str]:
    raw = os.getenv("BUFF_SEED_GOODS_IDS")
    if raw is not None:
        return [item.strip() for item in raw.split(",") if item.strip()]
    legacy_raw = os.getenv("BUFF_BUTTERFLY_SEEDS")
    if legacy_raw:
        return [item.strip() for item in legacy_raw.split(",") if item.strip()]
    return []


def get_search_keywords(track_keywords: list[str]) -> list[str | tuple[str, str | None]]:
    raw = os.getenv("BUFF_SEARCH_KEYWORDS")
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    expand_finishes = env_flag("BUFF_EXPAND_FINISH_SEARCHES", False)
    searches: list[str | tuple[str, str | None]] = []
    for knife in track_keywords:
        category = DEFAULT_KNIFE_CATEGORIES.get(knife)
        searches.append((knife, category))
        if expand_finishes:
            searches.extend((finish, category) for finish in DEFAULT_KNIFE_FINISHES)
    return searches
