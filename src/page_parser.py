from __future__ import annotations

import json
import re
from typing import Any

from market_utils import clean_html_text


def parse_goods_page_metadata(page: str, goods_id: str) -> dict[str, Any]:
    goods_info_match = re.search(
        r"var goods_info = (\{.*?\})\s*market_show\.pre_init", page, re.DOTALL
    )
    page_info: dict[str, Any] = {}
    if goods_info_match:
        page_info = json.loads(goods_info_match.group(1))

    image_match = re.search(r'<meta property="og:image" content="([^"]+)"', page)
    if image_match:
        page_info["image_url"] = image_match.group(1)

    top_segment_end = page.find('<div class="market-header black"')
    top_segment = page[:top_segment_end] if top_segment_end != -1 else page
    variant_ids: list[str] = []
    for match in re.finditer(
        r'<a class="[^"]*i_Btn[^"]*"[^>]*data-goodsid="(\d+)"[^>]*>(.*?)</a>',
        top_segment,
        re.DOTALL,
    ):
        inner_text = clean_html_text(match.group(2))
        if inner_text:
            variant_ids.append(match.group(1))

    page_info["variant_goods_ids"] = sorted(set(variant_ids + [str(goods_id)]))
    return page_info
