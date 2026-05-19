from __future__ import annotations

from typing import Any

from market_models import MarketSnapshot
from market_utils import normalize_image_url, split_market_name, try_float


def _first_number(*values: Any) -> float | None:
    for value in values:
        parsed = try_float(value)
        if parsed is not None:
            return parsed
    return None


def _count_from(item: dict[str, Any], info: dict[str, Any], keys: tuple[str, ...]) -> int:
    values = [source.get(key) for source in (item, info) for key in keys]
    value = _first_number(*values)
    return max(0, int(value)) if value is not None else 0


def build_sell_order_snapshot(
    *,
    goods_id: str,
    data: dict[str, Any],
    info: dict[str, Any],
    items: list[dict[str, Any]],
    page_meta: dict[str, Any] | None = None,
) -> MarketSnapshot:
    page_meta = page_meta or {}
    market_hash_name = info.get("market_hash_name") or info.get("name") or f"Goods {goods_id}"
    family, condition = split_market_name(market_hash_name)

    return MarketSnapshot(
        goods_id=str(goods_id),
        family=family,
        skin_name=f"{family} ({condition})" if condition and condition not in family else family,
        condition=condition or "Unknown",
        price=float(items[0]["price"]),
        listings=int(page_meta.get("sell_num") or data.get("total_count") or len(items)),
        buy_orders=int(page_meta.get("buy_num") or 0),
        reference_price=try_float(info.get("steam_price_cny")),
        image_url=normalize_image_url(
            info.get("original_icon_url")
            or info.get("icon_url")
            or page_meta.get("original_icon_url")
            or page_meta.get("icon_url")
            or page_meta.get("image_url")
        ),
        observed_orders=len(items),
    )


def build_market_item_snapshot(item: dict[str, Any]) -> MarketSnapshot | None:
    goods_id = item.get("id") or item.get("goods_id")
    if not goods_id:
        return None

    info = item.get("goods_info") or item
    market_hash_name = (
        info.get("market_hash_name")
        or item.get("market_hash_name")
        or info.get("name")
        or item.get("name")
        or ""
    )
    if not market_hash_name:
        return None

    family, condition = split_market_name(market_hash_name)
    price = try_float(
        item.get("sell_min_price") or item.get("quick_price") or item.get("sell_reference_price")
    )
    if price is None:
        return None

    return MarketSnapshot(
        goods_id=str(goods_id),
        family=family,
        skin_name=f"{family} ({condition})" if condition and condition not in family else family,
        condition=condition or "Unknown",
        price=price,
        listings=_count_from(
            item,
            info,
            ("sell_num", "sell_count", "sell_order_count", "sell_order_num", "total_count"),
        ),
        buy_orders=_count_from(
            item,
            info,
            ("buy_num", "buy_count", "buy_order_count", "buy_order_num"),
        ),
        reference_price=try_float(item.get("sell_reference_price") or info.get("steam_price_cny")),
        image_url=normalize_image_url(
            info.get("original_icon_url")
            or info.get("icon_url")
            or item.get("original_icon_url")
            or item.get("icon_url")
        ),
        observed_orders=0,
    )
