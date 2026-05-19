from __future__ import annotations

import os
import time
from typing import Any

import requests

from market_config import CONDITION_ORDER
from market_models import MarketSnapshot
from market_utils import debug_log, try_float


def discover_butterfly_catalog(client: Any, seed_goods_ids: list[str]) -> list[MarketSnapshot]:
    queue = [str(goods_id) for goods_id in seed_goods_ids]
    seen: set[str] = set()
    snapshots: dict[str, MarketSnapshot] = {}

    while queue:
        goods_id = queue.pop(0)
        if goods_id in seen:
            continue
        seen.add(goods_id)

        try:
            page_info = client.fetch_goods_page_metadata(goods_id)
        except Exception as exc:
            print(f"Failed to parse goods page {goods_id}: {exc}")
            continue

        for variant_id in page_info.get("variant_goods_ids", []):
            if variant_id not in seen and variant_id not in queue:
                queue.append(variant_id)

        try:
            snapshot = client.fetch_sell_snapshot(goods_id, page_meta=page_info)
        except Exception as exc:
            print(f"Failed to fetch goods {goods_id}: {exc}")
            continue

        if "Butterfly Knife" in snapshot.family:
            snapshots[goods_id] = snapshot
        time.sleep(0.35)

    return sorted(snapshots.values(), key=lambda item: (item.family, item.condition, item.goods_id))


def discover_high_value_catalog(
    client: Any,
    *,
    keywords: list[str | tuple[str, str | None]],
    min_price: float,
    seed_goods_ids: list[str] | None = None,
    max_pages_per_keyword: int = 20,
    match_keywords: list[str] | None = None,
    on_snapshot: Any | None = None,
    max_goods: int | None = None,
) -> list[MarketSnapshot]:
    queue = [str(goods_id) for goods_id in (seed_goods_ids or []) if str(goods_id).strip()]
    snapshots: dict[str, MarketSnapshot] = {}
    debug_log(
        "high_value_catalog start "
        f"keywords={len(keywords)} seeds={len(queue)} min_price={min_price} "
        f"max_pages_per_keyword={max_pages_per_keyword} max_goods={max_goods}"
    )
    for query in keywords:
        keyword, category = query if isinstance(query, tuple) else (query, None)
        before_keyword = len(snapshots)
        for snapshot in discover_snapshots_from_market(
            client,
            keyword=keyword,
            category=category,
            min_price=min_price,
            max_pages=max_pages_per_keyword,
        ):
            snapshots[snapshot.goods_id] = snapshot
            if on_snapshot is not None:
                on_snapshot(snapshot)
            if max_goods is not None and len(snapshots) >= max_goods:
                break
        if max_goods is not None and len(snapshots) >= max_goods:
            break
        queue.extend(
            discover_goods_ids_from_market(client, keyword=keyword, category=category, max_pages=0)
        )
        debug_log(
            "high_value_catalog keyword "
            f"keyword={keyword!r} category={category!r} added={len(snapshots) - before_keyword} "
            f"deduped_total={len(snapshots)} queue={len(queue)}"
        )
    queue = sorted(set(queue))

    seen: set[str] = set()
    raw_keywords = match_keywords or [
        value if isinstance(value, str) else value[0] for value in keywords
    ]
    keyword_lower = tuple(keyword.lower() for keyword in raw_keywords)

    while queue:
        if max_goods is not None and len(seen) >= max_goods:
            break
        goods_id = queue.pop(0)
        if goods_id in seen:
            continue
        seen.add(goods_id)

        try:
            page_info = client.fetch_goods_page_metadata(goods_id)
        except Exception as exc:
            print(f"Failed to parse goods page {goods_id}: {exc}")
            debug_log(f"high_value_catalog skip parse_failed goods_id={goods_id} error={exc}")
            continue

        for variant_id in page_info.get("variant_goods_ids", []):
            if variant_id not in seen and variant_id not in queue:
                queue.append(variant_id)

        try:
            snapshot = client.fetch_sell_snapshot(goods_id, page_meta=page_info)
        except Exception as exc:
            print(f"Failed to fetch goods {goods_id}: {exc}")
            debug_log(f"high_value_catalog skip fetch_failed goods_id={goods_id} error={exc}")
            continue

        family_lower = snapshot.family.lower()
        if snapshot.price >= min_price and any(
            keyword in family_lower for keyword in keyword_lower
        ):
            snapshots[goods_id] = snapshot
            if on_snapshot is not None:
                on_snapshot(snapshot)
        time.sleep(0.35)

    debug_log(f"high_value_catalog final snapshots={len(snapshots)} seen_variants={len(seen)}")
    return sorted(
        snapshots.values(),
        key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
    )


def discover_snapshots_from_market(
    client: Any,
    *,
    keyword: str,
    category: str | None = None,
    min_price: float,
    max_pages: int = 20,
) -> list[MarketSnapshot]:
    snapshots: dict[str, MarketSnapshot] = {}
    raw_total = 0
    parsed_total = 0
    price_filtered_total = 0
    invalid_total = 0
    duplicate_total = 0
    for page_num in range(1, max_pages + 1):
        response = client._get(
            client.GOODS_MARKET_URL,
            params={
                "game": "csgo",
                "search": keyword,
                **({"category": category} if category else {}),
                "min_price": str(int(min_price)),
                "page_num": page_num,
                "page_size": 80,
                "sort_by": "price.desc",
                "sort_order": "desc",
            },
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            print(f"Failed market search {keyword}: {exc}")
            break
        payload = response.json()
        if payload.get("code") != "OK":
            print(f"Failed market search {keyword}: BUFF code {payload.get('code')}")
            break

        data = payload.get("data") or {}
        items = data.get("items") or []
        raw_total += len(items)
        if not items:
            debug_log(
                "market_snapshots empty_page "
                f"keyword={keyword!r} category={category!r} page={page_num} raw_total={raw_total}"
            )
            break

        page_parsed = 0
        page_price_filtered = 0
        page_invalid = 0
        page_duplicates = 0
        for item in items:
            snapshot = client.market_item_snapshot(item)
            if snapshot is None:
                page_invalid += 1
                continue
            if snapshot.price < min_price:
                page_price_filtered += 1
                continue
            if snapshot.goods_id in snapshots:
                page_duplicates += 1
            snapshots[snapshot.goods_id] = snapshot
            page_parsed += 1
        parsed_total += page_parsed
        price_filtered_total += page_price_filtered
        invalid_total += page_invalid
        duplicate_total += page_duplicates
        debug_log(
            "market_snapshots page "
            f"keyword={keyword!r} category={category!r} page={page_num} "
            f"raw={len(items)} accepted={page_parsed} invalid={page_invalid} "
            f"price_filtered={page_price_filtered} duplicates={page_duplicates} "
            f"deduped_total={len(snapshots)}"
        )

        total_page = int(data.get("total_page") or 0)
        if total_page and page_num >= total_page:
            break
        time.sleep(float(os.getenv("BUFF_MARKET_PAGE_DELAY", "1.5")))

    debug_log(
        "market_snapshots final "
        f"keyword={keyword!r} category={category!r} raw={raw_total} accepted={parsed_total} "
        f"invalid={invalid_total} price_filtered={price_filtered_total} "
        f"duplicates={duplicate_total} deduped={len(snapshots)} max_pages={max_pages}"
    )
    return sorted(
        snapshots.values(),
        key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
    )


def discover_full_catalog(
    client: Any,
    *,
    keywords: list[str | tuple[str, str | None]],
    seed_goods_ids: list[str] | None = None,
    max_pages_per_keyword: int = 60,
    match_keywords: list[str] | None = None,
) -> list[MarketSnapshot]:
    queue = [str(goods_id) for goods_id in (seed_goods_ids or []) if str(goods_id).strip()]
    for query in keywords:
        keyword, category = query if isinstance(query, tuple) else (query, None)
        queue.extend(
            discover_goods_ids_from_market(
                client, keyword=keyword, category=category, max_pages=max_pages_per_keyword
            )
        )
    queue = sorted(set(queue))

    seen: set[str] = set()
    snapshots: dict[str, MarketSnapshot] = {}
    raw_keywords = match_keywords or [
        value if isinstance(value, str) else value[0] for value in keywords
    ]
    keyword_lower = tuple(keyword.lower() for keyword in raw_keywords)

    while queue:
        goods_id = queue.pop(0)
        if goods_id in seen:
            continue
        seen.add(goods_id)

        try:
            page_info = client.fetch_goods_page_metadata(goods_id)
        except Exception as exc:
            print(f"Failed to parse goods page {goods_id}: {exc}")
            continue

        for variant_id in page_info.get("variant_goods_ids", []):
            if variant_id not in seen and variant_id not in queue:
                queue.append(variant_id)

        try:
            snapshot = client.fetch_sell_snapshot(goods_id, page_meta=page_info)
        except Exception as exc:
            print(f"Failed to fetch goods {goods_id}: {exc}")
            continue

        family_lower = snapshot.family.lower()
        if any(keyword in family_lower for keyword in keyword_lower):
            snapshots[goods_id] = snapshot
        time.sleep(0.25)

    return sorted(
        snapshots.values(),
        key=lambda item: (item.family, CONDITION_ORDER.get(item.condition, 50), item.goods_id),
    )


def discover_goods_ids_from_market(
    client: Any,
    *,
    keyword: str,
    category: str | None = None,
    max_pages: int = 20,
    min_price: float | None = None,
) -> list[str]:
    goods_ids: set[str] = set()
    raw_total = 0
    price_filtered_total = 0
    missing_id_total = 0
    duplicate_total = 0
    for page_num in range(1, max_pages + 1):
        response = client._get(
            client.GOODS_MARKET_URL,
            params={
                "game": "csgo",
                "search": keyword,
                "use_suggestion": "0",
                **({"category": category} if category else {}),
                "page_num": page_num,
                "page_size": 80,
                "sort_by": "price.desc",
                "sort_order": "desc",
            },
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            print(f"Failed market search {keyword}: {exc}")
            break
        payload = response.json()
        if payload.get("code") != "OK":
            break
        data = payload.get("data") or {}
        items = data.get("items") or []
        raw_total += len(items)
        if not items:
            break

        page_price_filtered = 0
        page_missing_id = 0
        page_duplicates = 0
        for item in items:
            item_price = try_float(
                item.get("sell_min_price")
                or item.get("quick_price")
                or item.get("sell_reference_price")
                or item.get("steam_price_cny")
            )
            if min_price is not None and item_price is not None and item_price < min_price:
                page_price_filtered += 1
                continue
            goods_id = item.get("id") or item.get("goods_id")
            if goods_id:
                if str(goods_id) in goods_ids:
                    page_duplicates += 1
                goods_ids.add(str(goods_id))
            else:
                page_missing_id += 1
        price_filtered_total += page_price_filtered
        missing_id_total += page_missing_id
        duplicate_total += page_duplicates
        debug_log(
            "market_goods_ids page "
            f"keyword={keyword!r} category={category!r} page={page_num} raw={len(items)} "
            f"price_filtered={page_price_filtered} missing_id={page_missing_id} "
            f"duplicates={page_duplicates} deduped_total={len(goods_ids)}"
        )

        total_page = int(data.get("total_page") or 0)
        if total_page and page_num >= total_page:
            break
        time.sleep(0.2)

    debug_log(
        "market_goods_ids final "
        f"keyword={keyword!r} category={category!r} raw={raw_total} "
        f"price_filtered={price_filtered_total} missing_id={missing_id_total} "
        f"duplicates={duplicate_total} deduped={len(goods_ids)} max_pages={max_pages}"
    )
    return sorted(goods_ids)
