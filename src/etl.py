from __future__ import annotations

from typing import Any

import pandas as pd

from market_config import HISTORY_HEADERS
from market_utils import canonicalize_family_name, split_market_name


def parse_family_and_condition(row: dict[str, Any]) -> tuple[str, str]:
    family = str(row.get("Family") or "").strip()
    condition = str(row.get("Condition") or "").strip()
    skin_name = str(row.get("Skin Name") or "").strip()
    family = canonicalize_family_name(family)
    skin_name = canonicalize_family_name(skin_name)
    if family and condition:
        return family, condition
    if skin_name:
        derived_family, derived_condition = split_market_name(skin_name)
        return canonicalize_family_name(family or derived_family), condition or derived_condition
    return family, condition


def normalize_history_values(raw_values: list[list[Any]]) -> pd.DataFrame:
    if not raw_values:
        return pd.DataFrame(columns=HISTORY_HEADERS)

    headers = [str(cell).strip() for cell in raw_values[0]]
    rows = raw_values[1:]

    def find_index(*candidates: str) -> int | None:
        lowered = [header.lower() for header in headers]
        for candidate in candidates:
            candidate_lower = candidate.lower()
            for idx, header in enumerate(lowered):
                if header == candidate_lower:
                    return idx
            for idx, header in enumerate(lowered):
                if candidate_lower in header:
                    return idx
        return None

    timestamp_idx = find_index("Timestamp")
    goods_id_idx = find_index("Goods ID", "GoodsId")
    family_idx = find_index("Family")
    knife_type_idx = find_index("Knife Type", "Knife")
    skin_name_idx = find_index("Skin Name", "Skin")
    condition_idx = find_index("Condition")
    price_idx = find_index("Price")
    listings_idx = find_index("Listings", "Sell Listings")
    buy_orders_idx = find_index("Buy Orders", "Buy Order")
    reference_price_idx = find_index("Reference Price", "Steam Price")
    image_url_idx = find_index("Image URL", "Icon URL")
    observed_orders_idx = find_index("Observed Orders", "Sample Size", "Observed")

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not any(str(cell).strip() for cell in row):
            continue

        def cell(idx: int | None) -> str:
            if idx is None or idx >= len(row):
                return ""
            return str(row[idx]).strip()

        normalized = {
            "Timestamp": cell(timestamp_idx),
            "Goods ID": cell(goods_id_idx),
            "Family": cell(family_idx),
            "Knife Type": cell(knife_type_idx),
            "Skin Name": cell(skin_name_idx),
            "Condition": cell(condition_idx),
            "Price": cell(price_idx).replace(",", "."),
            "Listings": cell(listings_idx),
            "Buy Orders": cell(buy_orders_idx),
            "Reference Price": cell(reference_price_idx),
            "Image URL": cell(image_url_idx),
            "Observed Orders": cell(observed_orders_idx),
        }
        family, condition = parse_family_and_condition(normalized)
        normalized["Family"] = family
        normalized["Condition"] = condition
        if not normalized["Knife Type"] and family:
            normalized["Knife Type"] = family.split("|")[0].strip()
        if family and condition:
            normalized["Skin Name"] = f"{family} ({condition})"
        elif family:
            normalized["Skin Name"] = family
        normalized_rows.append(normalized)

    return pd.DataFrame(normalized_rows, columns=HISTORY_HEADERS)
