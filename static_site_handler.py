from __future__ import annotations

import gzip
import hashlib
import html
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

CSGOTRADER_BUFF_URL = "https://prices.csgotrader.app/latest/buff163.json"
CSGO_API_SKINS_URL = (
    "https://raw.githubusercontent.com/ByMykel/CSGO-API/main/public/api/en/skins.json"
)
DEFAULT_TRACK_KEYWORDS = [
    "Bayonet",
    "Bowie Knife",
    "Butterfly Knife",
    "Classic Knife",
    "Falchion Knife",
    "Flip Knife",
    "Gut Knife",
    "Huntsman Knife",
    "Karambit",
    "Kukri Knife",
    "M9 Bayonet",
    "Navaja Knife",
    "Nomad Knife",
    "Paracord Knife",
    "Shadow Daggers",
    "Skeleton Knife",
    "Stiletto Knife",
    "Survival Knife",
    "Talon Knife",
    "Ursus Knife",
]
CONDITION_ORDER = {
    "Factory New": 0,
    "Minimal Wear": 1,
    "Field-Tested": 2,
    "Well-Worn": 3,
    "Battle-Scarred": 4,
    "StatTrak": 5,
    "Unknown": 99,
}
CONDITIONS = tuple(CONDITION_ORDER)
MIN_VALID_PRICE_CNY = Decimal("1")
WEAR_ABBREVIATIONS = {
    "Factory New": "FN",
    "Minimal Wear": "MW",
    "Field-Tested": "FT",
    "Well-Worn": "WW",
    "Battle-Scarred": "BS",
    "StatTrak": "ST",
    "Unknown": "N/A",
}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [part.strip() for part in raw.split(",") if part.strip()]


def _fetch_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept-Encoding": "gzip",
            "User-Agent": "buff163-free-tier-site/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed trusted URL
        body = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            body = gzip.decompress(body)
        return json.loads(body.decode("utf-8"))


def _split_market_name(name: str) -> tuple[str, str]:
    for condition in CONDITIONS:
        suffix = f"({condition})"
        if name.endswith(suffix):
            return name[: -len(suffix)].strip(), condition
    return name.strip(), "Unknown"


def _source_id(name: str) -> str:
    return "csgotrader:" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]


def _decimal_or_none(value: Any) -> Decimal | None:
    try:
        if value in (None, ""):
            return None
        price = Decimal(str(value).replace(",", "").strip())
    except Exception:
        return None
    return price if price.is_finite() else None


def _number_or_none(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", "").strip())
    except Exception:
        return None
    return number if number == number else None


def _static_item_image_url(name: str) -> str:
    label = html.escape(name[:2].upper() if name else "K")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 120">'
        "<defs>"
        '<linearGradient id="g" x1="0" x2="1" y1="0" y2="1">'
        '<stop offset="0" stop-color="#f5b342"/><stop offset=".55" stop-color="#ff7a1a"/>'
        '<stop offset="1" stop-color="#111827"/>'
        "</linearGradient>"
        '<filter id="s" x="-20%" y="-20%" width="140%" height="140%">'
        '<feDropShadow dx="0" dy="10" stdDeviation="8" flood-color="#000" flood-opacity=".45"/>'
        "</filter>"
        "</defs>"
        '<rect width="160" height="120" rx="18" fill="#0b101a"/>'
        '<path d="M119 21 139 41 70 110 45 115 50 90Z" fill="url(#g)" filter="url(#s)"/>'
        '<path d="M47 82 78 113" stroke="#f8d08a" stroke-width="8" stroke-linecap="round"/>'
        '<text x="20" y="38" fill="#f8d08a" font-family="Arial, sans-serif" '
        f'font-size="20" font-weight="700">{label}</text>'
        "</svg>"
    )
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg, safe="/:=#;,%?&+")


def _csgo_api_image_map() -> dict[str, str]:
    if os.getenv("BUFF_FILL_IMAGES", "1").strip().lower() not in {"1", "true", "yes", "on"}:
        return {}
    try:
        payload = _fetch_json(CSGO_API_SKINS_URL)
    except Exception as exc:
        print(f"image_map_fetch_failed={type(exc).__name__}: {exc}", flush=True)
        return {}

    images: dict[str, str] = {}
    for item in payload if isinstance(payload, list) else []:
        name = str((item or {}).get("name") or "").replace("\u2605", "").strip()
        image = str((item or {}).get("image") or "").strip()
        if not name or not image:
            continue
        images[name] = image
        for wear in (item or {}).get("wears") or []:
            wear_name = str((wear or {}).get("name") or "").strip()
            if wear_name:
                images[f"{name} ({wear_name})"] = image
    return images


def _strip_variant_prefix(name: str) -> str:
    """Drop StatTrak / Souvenir prefixes so variants reuse the base skin image.

    csgo-api lists one image per base skin; StatTrak and Souvenir versions share
    the same artwork, so matching on the base name fills most missing images.
    """
    out = name
    for prefix in ("StatTrak™ ", "StatTrak ", "Souvenir "):
        if out.startswith(prefix):
            out = out[len(prefix):]
    return out.strip()


def _lookup_image(image_map: dict[str, str], clean_name: str, full_name: str) -> str:
    """Try full name, base name (no wear), then variant-stripped forms."""
    base_full = _strip_variant_prefix(full_name)
    base_clean = _strip_variant_prefix(clean_name)
    for key in (clean_name, full_name, base_clean, base_full):
        hit = image_map.get(key)
        if hit:
            return hit
    return ""


def _match_knife_type(name: str, keywords: list[str]) -> str | None:
    clean_name = name.lower()
    for keyword in sorted(keywords, key=len, reverse=True):
        if keyword.lower() in clean_name:
            return keyword
    return None


def _money(value: Any) -> str:
    number = _number_or_none(value)
    return "N/A" if number is None else f"{number:,.2f} CNY"


def _spread(row: dict[str, Any]) -> str:
    price = _number_or_none(row.get("price") or row.get("price_cny"))
    reference = _number_or_none(row.get("reference_price_cny"))
    if price is None or reference is None or price <= 0:
        return "N/A"
    percent = ((price - reference) / price) * 100
    return f"{percent:+.1f}%"


def _table_row_html(row: dict[str, Any]) -> str:
    image_url = html.escape(
        str(row.get("image_url") or _static_item_image_url(str(row.get("knife_type") or "Knife")))
    )
    item_name = html.escape(str(row.get("item_name") or row.get("skin_name") or "Unknown item"))
    family = html.escape(str(row.get("knife_type") or row.get("family") or "Unknown"))
    condition = html.escape(str(row.get("condition") or "N/A"))
    wear = html.escape(str(row.get("wear") or row.get("condition") or "N/A"))
    source = html.escape(str(row.get("source") or ""))
    goods_id = html.escape(str(row.get("goods_id") or ""))
    lc = row.get("listing_count")
    listing = f"{int(lc):,}" if isinstance(lc, (int, float)) else "N/A"
    return (
        f'<tr data-id="{goods_id}"><td><div class="skin-cell">'
        f'<img class="skin-thumb" src="{image_url}" alt="" loading="lazy" '
        f"onerror=\"this.onerror=null;this.src=FALLBACK_IMG\">"
        f"<div><strong>{item_name}</strong><small>{family} &middot; {condition}</small></div>"
        f'</div></td><td><span class="pill">{wear}</span></td>'
        f'<td class="right">{_money(row.get("price") or row.get("price_cny"))}</td>'
        f'<td class="right">{_money(row.get("reference_price_cny"))}</td>'
        f'<td>{_spread(row)}</td>'
        f'<td class="right">{listing}</td>'
        f"<td>{source}</td></tr>"
    )


def _validate_static_payload(rows: list[dict[str, Any]], html_body: str) -> None:
    invalid_prices = [
        row
        for row in rows
        if (price := _number_or_none(row.get("price") or row.get("price_cny"))) is None
        or price < float(MIN_VALID_PRICE_CNY)
    ]
    if invalid_prices:
        raise ValueError(f"static payload contains invalid prices: {len(invalid_prices)}")
    if rows and '<tbody id="rows"><tr' not in html_body:
        raise ValueError("static table would render 0 initial rows for a non-empty dataset")
    missing_images = [row for row in rows if not str(row.get("image_url") or "").strip()]
    if missing_images:
        raise ValueError(f"static payload missing image fallback: {len(missing_images)}")
    missing_category = [row for row in rows if not str(row.get("category") or "").strip()]
    if missing_category:
        raise ValueError(f"static payload missing category fallback: {len(missing_category)}")
    missing_wear = [row for row in rows if not str(row.get("wear") or "").strip()]
    if missing_wear:
        raise ValueError(f"static payload missing wear fallback: {len(missing_wear)}")


def _snapshots() -> list[dict[str, Any]]:
    usd_to_cny = Decimal(os.getenv("BUFF_USD_CNY", "7.2"))
    configured_min_price = _decimal_or_none(os.getenv("BUFF_MIN_PRICE_CNY", "0")) or Decimal("0")
    min_price = max(configured_min_price, MIN_VALID_PRICE_CNY)
    keywords = _env_list("BUFF_TRACK_KEYWORDS", DEFAULT_TRACK_KEYWORDS)
    payload = _fetch_json(CSGOTRADER_BUFF_URL)
    image_map = _csgo_api_image_map()
    rows: list[dict[str, Any]] = []
    for raw_name, value in payload.items():
        clean_name = str(raw_name).replace("\u2605", "").strip()
        knife_type = _match_knife_type(clean_name, keywords)
        if not knife_type:
            continue
        starting_at = value.get("starting_at") or {}
        highest_order = value.get("highest_order") or {}
        price_usd = _decimal_or_none(starting_at.get("price"))
        if price_usd is None:
            continue
        price = price_usd * usd_to_cny
        if price < min_price:
            continue
        full_name, condition = _split_market_name(clean_name)
        # Drop the upstream summary rows that aggregate a knife with no wear
        # (e.g. base "Bayonet" without a specific skin/condition). They pollute
        # the table with N/A wear and have no real per-skin meaning.
        if condition == "Unknown":
            continue
        reference_price = None
        highest_order_price = _decimal_or_none(highest_order.get("price"))
        if highest_order_price is not None:
            reference_price = float(highest_order_price * usd_to_cny)
        image_url = _lookup_image(image_map, clean_name, full_name)
        image_fallback_url = _static_item_image_url(knife_type)
        wear = WEAR_ABBREVIATIONS.get(condition, condition or "N/A")
        price_cny = round(float(price), 2)
        reference_price_cny = round(reference_price, 2) if reference_price else None
        # family = weapon (e.g. "Bayonet"), skin_name = full ("Bayonet | Autotronic (Factory New)")
        family = knife_type
        rows.append(
            {
                "goods_id": _source_id(clean_name),
                "market_hash_name": clean_name,
                "item_name": full_name,  # e.g. "Bayonet | Autotronic"
                "skin_name": f"{full_name} ({condition})",
                "knife_type": knife_type,
                "weapon_type": "Knife",
                "category": knife_type,
                "family": family,  # weapon only (e.g. "Bayonet")
                "condition": condition,
                "condition_short": wear,
                "wear": wear,
                "price": price_cny,
                "price_cny": price_cny,
                "reference_price_cny": reference_price_cny,
                "spread_percent": (
                    round(((price_cny - reference_price_cny) / price_cny) * 100, 2)
                    if price_cny and reference_price_cny
                    else None
                ),
                # csgotrader public feed does not include order-book depth.
                # Use null (unknown), NOT 0 (which would mean confirmed zero listings).
                "listing_count": None,
                "sell_min_price": price_cny,
                "buy_max_price": (
                    float(highest_order_price * usd_to_cny)
                    if highest_order_price is not None
                    else None
                ),
                # buff_url: goods_id from csgotrader is a content hash, not a BUFF
                # numeric id. Frontend opens a search URL using market_hash_name instead.
                "buff_url": None,
                "image_url": image_url or image_fallback_url,
                "has_source_image": bool(image_url),
                "source": "csgotrader buff163",
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["knife_type"],
            row["family"],
            CONDITION_ORDER.get(str(row["condition"]), 50),
            row["goods_id"],
        ),
    )


def _data_quality(rows: list[dict[str, Any]], iso_now: str) -> dict[str, Any]:
    """Coverage report. Listing_count = null counts as unknown, not zero."""
    total = len(rows)
    with_price = sum(1 for r in rows if isinstance(r.get("price_cny"), (int, float)) and r["price_cny"] > 0)
    with_ref = sum(1 for r in rows if isinstance(r.get("reference_price_cny"), (int, float)))
    with_listing = sum(1 for r in rows if r.get("listing_count") is not None)
    unknown_listing = total - with_listing
    with_image = sum(1 for r in rows if r.get("image_url"))
    with_goods_id = sum(1 for r in rows if r.get("goods_id"))
    families = {str(r.get("family") or "Unknown") for r in rows}
    return {
        "generated_at": iso_now,
        "total_items": total,
        "items_with_price": with_price,
        "items_with_reference_price": with_ref,
        "items_with_listing_count": with_listing,
        "items_with_unknown_listing_count": unknown_listing,
        "items_with_image": with_image,
        "items_with_goods_id": with_goods_id,
        "families_count": len(families),
        "source": "csgotrader buff163",
        "warnings": (
            ["listing_count unavailable from upstream feed; values shown as N/A"]
            if unknown_listing == total and total > 0
            else []
        ),
    }


def _market_summary(rows: list[dict[str, Any]], iso_now: str) -> dict[str, Any]:
    """Global summary for the dashboard hero / KPI cards."""
    prices = [r["price_cny"] for r in rows if isinstance(r.get("price_cny"), (int, float)) and r["price_cny"] > 0]
    families = {str(r.get("family") or "Unknown") for r in rows}
    highest = max(rows, key=lambda r: (r.get("price_cny") or 0), default=None)
    lowest = min(
        (r for r in rows if isinstance(r.get("price_cny"), (int, float)) and r["price_cny"] > 0),
        key=lambda r: r["price_cny"],
        default=None,
    )
    # Most listed only meaningful when listing_count is known.
    listed = [r for r in rows if isinstance(r.get("listing_count"), (int, float))]
    most_listed = max(listed, key=lambda r: r["listing_count"], default=None) if listed else None
    return {
        "generated_at": iso_now,
        "total_items": len(rows),
        "total_families": len(families),
        "average_price_cny": round(sum(prices) / len(prices), 2) if prices else None,
        "highest_price_item": _summary_item(highest),
        "lowest_price_item": _summary_item(lowest),
        "most_listed_item": _summary_item(most_listed),
    }


def _summary_item(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "goods_id": row.get("goods_id"),
        "item_name": row.get("item_name"),
        "family": row.get("family"),
        "condition": row.get("condition"),
        "price_cny": row.get("price_cny"),
        "listing_count": row.get("listing_count"),
    }


def _families_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-family aggregation for the family cards section."""
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        family = str(row.get("knife_type") or "Unknown")
        by_family.setdefault(family, []).append(row)
    summary: list[dict[str, Any]] = []
    for family, items in by_family.items():
        prices = [r["price_cny"] for r in items if isinstance(r.get("price_cny"), (int, float)) and r["price_cny"] > 0]
        listed = [r for r in items if isinstance(r.get("listing_count"), (int, float))]
        first_image = next((r.get("image_url") for r in items if r.get("image_url")), "")
        summary.append(
            {
                "family": family,
                "item_count": len(items),
                "average_price_cny": round(sum(prices) / len(prices), 2) if prices else None,
                "min_price_cny": min(prices) if prices else None,
                "max_price_cny": max(prices) if prices else None,
                "total_listings": sum(r["listing_count"] for r in listed) if listed else None,
                "image_url": first_image or _static_item_image_url(family),
            }
        )
    return sorted(summary, key=lambda f: (-f["item_count"], f["family"]))


def _render_html(updated_at: str, rows: list[dict[str, Any]]) -> str:
    count = len(rows)
    prices = [
        price
        for row in rows
        if (price := _number_or_none(row.get("price") or row.get("price_cny"))) is not None
        and price >= float(MIN_VALID_PRICE_CNY)
    ]
    avg_price = sum(prices) / len(prices) if prices else 0
    high_price = max(prices) if prices else 0
    low_price = min(prices) if prices else 0
    premium_rows = sum(1 for price in prices if price >= avg_price) if avg_price else 0
    family_counts: dict[str, int] = {}
    knife_type_counts: dict[str, int] = {}
    for row in rows:
        family = str(row["family"])
        family_counts[family] = family_counts.get(family, 0) + 1
        knife_type = str(row.get("knife_type", "Unknown"))
        knife_type_counts[knife_type] = knife_type_counts.get(knife_type, 0) + 1
    top_family = max(family_counts, key=family_counts.get) if family_counts else "No data"
    top_knife_type = (
        max(knife_type_counts, key=knife_type_counts.get) if knife_type_counts else "No data"
    )
    knife_types = []
    for name in DEFAULT_TRACK_KEYWORDS:
        count_for_type = knife_type_counts.get(name, 0)
        if not count_for_type:
            continue
        representative_image = next(
            (
                str(row.get("image_url") or "")
                for row in rows
                if row.get("knife_type") == name and row.get("image_url")
            ),
            "",
        )
        knife_types.append(
            {
                "name": name,
                "count": count_for_type,
                "image_url": representative_image or _static_item_image_url(name),
                "has_source_image": bool(representative_image),
            }
        )
    payload = json.dumps(rows, separators=(",", ":")).replace("</", "<\\/")
    knife_types_payload = json.dumps(knife_types, separators=(",", ":")).replace("</", "<\\/")
    initial_rows_html = "".join(_table_row_html(row) for row in rows[:300])
    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>BUFF163 Market Intelligence</title>
  <style>
    :root {
      --bg: #080b12;
      --panel: rgba(17, 24, 39, .76);
      --panel-strong: rgba(25, 34, 49, .92);
      --line: rgba(255,255,255,.11);
      --line-strong: rgba(245, 158, 11, .32);
      --text: #f5f7fb;
      --muted: #9aa8bd;
      --gold: #f5b342;
      --orange: #ff7a1a;
      --green: #56d89a;
      --red: #ff6b6b;
      --blue: #79a9ff;
      --shadow: 0 24px 70px rgba(0,0,0,.42);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 18% 4%, rgba(245, 179, 66, .18), transparent 30%),
        radial-gradient(circle at 88% 10%, rgba(255, 122, 26, .16), transparent 28%),
        linear-gradient(145deg, #070911 0%, #0d1320 48%, #06080d 100%);
      color: var(--text);
      letter-spacing: 0;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px);
      background-size: 44px 44px;
      mask-image: linear-gradient(to bottom, rgba(0,0,0,.72), transparent 78%);
    }
    main { position: relative; width: min(1240px, calc(100% - 32px)); margin: 0 auto; padding: 30px 0 56px; }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
      color: var(--muted);
      font-size: 13px;
    }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 800; color: #fff; }
    .mark {
      width: 34px; height: 34px; border-radius: 8px;
      display: grid; place-items: center;
      background: linear-gradient(135deg, var(--gold), var(--orange));
      color: #1a1004; box-shadow: 0 12px 32px rgba(245, 179, 66, .28);
    }
    .hero {
      position: relative;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 30px;
      background:
        linear-gradient(135deg, rgba(255,255,255,.095), rgba(255,255,255,.032)),
        radial-gradient(circle at 78% 12%, rgba(245, 179, 66, .24), transparent 34%),
        rgba(10, 14, 23, .72);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }
    .hero::after {
      content: "";
      position: absolute;
      inset: auto -80px -120px auto;
      width: 360px; height: 360px;
      background: conic-gradient(from 180deg, rgba(245,179,66,.22), rgba(255,122,26,.08), transparent, rgba(245,179,66,.2));
      border-radius: 50%;
      filter: blur(18px);
      opacity: .75;
    }
    .hero-grid { position: relative; z-index: 1; display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(280px, .7fr); gap: 24px; align-items: end; }
    h1 { margin: 0; max-width: 780px; font-size: clamp(34px, 5vw, 64px); line-height: 1; letter-spacing: 0; }
    .subtitle { max-width: 720px; margin: 18px 0 0; color: #c5cedd; font-size: 17px; line-height: 1.65; }
    .badge-row { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }
    .badge {
      display: inline-flex; align-items: center; gap: 8px;
      min-height: 34px; padding: 7px 11px; border: 1px solid var(--line);
      border-radius: 999px; background: rgba(255,255,255,.07); color: #e8eef9; font-size: 13px;
    }
    .badge.live { border-color: rgba(86,216,154,.36); color: #b9f8d7; background: rgba(86,216,154,.09); }
    .dot { width: 8px; height: 8px; border-radius: 999px; background: var(--green); box-shadow: 0 0 18px var(--green); }
    .hero-card {
      border: 1px solid var(--line-strong);
      border-radius: 14px;
      padding: 18px;
      background: rgba(7, 10, 16, .62);
    }
    .hero-card span, .metric span, .panel-kicker { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .hero-card strong { display: block; margin-top: 8px; font-size: 34px; }
    .hero-card p { margin: 12px 0 0; color: #c4cedc; line-height: 1.5; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin: 18px 0;
    }
    .metric, .panel {
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--panel);
      box-shadow: 0 16px 44px rgba(0,0,0,.28);
      backdrop-filter: blur(16px);
    }
    .metric { padding: 17px; transition: transform .18s ease, border-color .18s ease, background .18s ease; }
    .metric:hover, tr:hover { transform: translateY(-2px); border-color: var(--line-strong); background: rgba(25, 34, 49, .86); }
    .metric-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .icon {
      width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center;
      background: linear-gradient(135deg, rgba(245,179,66,.23), rgba(255,122,26,.12));
      color: var(--gold);
    }
    .metric strong { display: block; margin-top: 14px; font-size: clamp(22px, 3vw, 32px); }
    .trend { margin-top: 8px; color: #b7c3d6; font-size: 13px; }
    .trend.up { color: var(--green); }
    .trend.warn { color: var(--gold); }
    .coverage {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      align-items: center;
      margin: 18px 0;
      padding: 16px;
    }
    .family-rail { display: flex; gap: 9px; overflow-x: auto; padding-bottom: 3px; scrollbar-width: thin; }
    button, input, select { font: inherit; }
    button {
      cursor: pointer;
      border: 1px solid var(--line);
      color: var(--text);
      background: rgba(255,255,255,.055);
      transition: transform .18s ease, border-color .18s ease, background .18s ease, color .18s ease;
    }
    button:hover { transform: translateY(-1px); border-color: var(--line-strong); background: rgba(245,179,66,.11); }
    button:focus-visible, input:focus-visible, select:focus-visible {
      outline: 2px solid var(--gold);
      outline-offset: 2px;
    }
    .family-chip {
      flex: 0 0 auto;
      min-height: 54px;
      border-radius: 14px;
      padding: 8px 12px 8px 8px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
    }
    .family-chip img {
      width: 42px;
      height: 34px;
      object-fit: contain;
      filter: drop-shadow(0 8px 12px rgba(0,0,0,.45));
    }
    .family-chip.active {
      color: #1a1004;
      border-color: rgba(245,179,66,.72);
      background: linear-gradient(135deg, var(--gold), var(--orange));
      box-shadow: 0 10px 28px rgba(245,179,66,.18);
    }
    .chip-count {
      min-width: 24px;
      border-radius: 999px;
      padding: 2px 7px;
      background: rgba(0,0,0,.24);
      color: inherit;
      font-size: 12px;
    }
    .knife-atlas {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }
    .knife-card {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 13px;
      min-height: 172px;
      background: linear-gradient(145deg, rgba(255,255,255,.07), rgba(255,255,255,.025));
      display: grid;
      grid-template-rows: 1fr auto;
      gap: 10px;
      transition: transform .18s ease, border-color .18s ease, background .18s ease;
    }
    .knife-card:hover {
      transform: translateY(-2px);
      border-color: var(--line-strong);
      background: rgba(245,179,66,.08);
    }
    .knife-art {
      width: 100%;
      height: 94px;
      object-fit: contain;
      filter: drop-shadow(0 18px 18px rgba(0,0,0,.5));
    }
    .knife-card strong { display: block; font-size: 14px; }
    .knife-card span { display: block; margin-top: 4px; color: var(--muted); font-size: 12px; }
    .item-detail {
      margin-top: 16px;
      display: grid;
      grid-template-columns: minmax(260px, .85fr) minmax(0, 1.15fr);
      gap: 22px;
      align-items: stretch;
    }
    .detail-media {
      min-height: 310px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background:
        radial-gradient(circle at 50% 18%, rgba(245,179,66,.18), transparent 44%),
        rgba(7, 10, 16, .48);
      display: grid;
      place-items: center;
      padding: 22px;
    }
    .detail-art {
      width: min(100%, 420px);
      max-height: 270px;
      object-fit: contain;
      filter: drop-shadow(0 28px 28px rgba(0,0,0,.56));
    }
    .detail-content { display: flex; flex-direction: column; justify-content: space-between; gap: 18px; }
    .detail-title h2 { margin: 8px 0 0; font-size: clamp(28px, 4vw, 44px); line-height: 1.04; }
    .detail-meta, .wear-row, .detail-prices { display: flex; flex-wrap: wrap; gap: 10px; }
    .detail-prices { align-items: stretch; }
    .price-tile {
      flex: 1 1 180px;
      border: 1px solid var(--line);
      border-radius: 13px;
      padding: 14px;
      background: rgba(255,255,255,.045);
    }
    .price-tile span { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .price-tile strong { display: block; margin-top: 8px; font-size: 24px; }
    .wear-button {
      min-width: 54px;
      min-height: 40px;
      border-radius: 10px;
      color: #ffd58a;
    }
    .wear-button.active {
      color: #1a1004;
      border-color: rgba(245,179,66,.72);
      background: linear-gradient(135deg, var(--gold), var(--orange));
    }
    .related-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .related-card {
      border: 1px solid var(--line);
      border-radius: 13px;
      padding: 12px;
      background: rgba(255,255,255,.045);
      display: grid;
      grid-template-columns: 66px 1fr;
      gap: 10px;
      align-items: center;
      text-align: left;
      min-height: 92px;
    }
    .related-card img {
      width: 66px;
      height: 52px;
      object-fit: contain;
      filter: drop-shadow(0 10px 12px rgba(0,0,0,.38));
    }
    .related-card strong { display: block; font-size: 13px; }
    .related-card span { display: block; margin-top: 4px; color: var(--muted); font-size: 12px; }
    .layout { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(320px, .8fr); gap: 16px; margin-top: 16px; }
    .panel { padding: 18px; overflow: hidden; }
    .panel-title { display: flex; align-items: start; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
    .panel h2 { margin: 4px 0 0; font-size: 20px; }
    .panel p { color: var(--muted); line-height: 1.55; }
    .chart-wrap { height: 290px; position: relative; }
    svg.chart { width: 100%; height: 100%; display: block; }
    .axis, .chart-label { fill: #8190a7; font-size: 11px; }
    .line { fill: none; stroke: url(#priceGradient); stroke-width: 3; }
    .area { fill: url(#areaGradient); opacity: .86; }
    .bar { fill: url(#barGradient); rx: 6; opacity: .9; }
    .empty-state {
      min-height: 230px; display: grid; place-items: center; text-align: center;
      border: 1px dashed rgba(255,255,255,.16); border-radius: 12px;
      background: rgba(255,255,255,.035); padding: 20px;
    }
    .insight-list { display: grid; gap: 12px; margin-top: 14px; }
    .insight {
      padding: 13px; border: 1px solid var(--line); border-radius: 12px;
      background: rgba(255,255,255,.045);
    }
    .insight strong { display: block; margin-bottom: 6px; }
    .table-tools { display: grid; grid-template-columns: 1fr 180px 170px 180px auto; gap: 10px; margin-bottom: 14px; }
    .reset-btn { min-height: 38px; padding: 0 14px; border-radius: 10px; color: #c8dcff; }
    input, select {
      width: 100%; min-height: 42px; border-radius: 10px; border: 1px solid rgba(255,255,255,.13);
      background: rgba(7, 10, 16, .72); color: var(--text); padding: 10px 12px;
      outline: none;
    }
    input:focus, select:focus { border-color: var(--gold); box-shadow: 0 0 0 3px rgba(245,179,66,.12); }
    .table-shell { overflow-x: auto; border: 1px solid var(--line); border-radius: 12px; }
    table { width: 100%; border-collapse: collapse; min-width: 760px; font-size: 14px; }
    th, td { padding: 13px 14px; border-bottom: 1px solid rgba(255,255,255,.08); text-align: left; }
    th { color: #aeb9ca; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; background: rgba(255,255,255,.04); }
    td { color: #e8eef9; }
    tr { transition: transform .18s ease, background .18s ease; }
    tbody tr { cursor: pointer; }
    tbody tr:hover,
    tbody tr.selected-row {
      background: rgba(245,179,66,.08);
    }
    tbody tr.selected-row {
      box-shadow: inset 3px 0 0 rgba(245,179,66,.72);
    }
    .right { text-align: right; }
    .skin-cell { display: grid; grid-template-columns: 48px 1fr; align-items: center; gap: 10px; }
    .skin-thumb {
      width: 48px;
      height: 38px;
      object-fit: contain;
      border-radius: 8px;
      background: rgba(255,255,255,.045);
      border: 1px solid rgba(255,255,255,.08);
      padding: 3px;
      filter: drop-shadow(0 8px 10px rgba(0,0,0,.35));
    }
    .skin-cell small { color: var(--muted); }
    .pill {
      display: inline-flex; align-items: center; justify-content: center;
      border-radius: 999px; padding: 5px 9px; background: rgba(245,179,66,.12);
      color: #ffd58a; border: 1px solid rgba(245,179,66,.2); white-space: nowrap;
    }
    .liquidity {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 4px 9px; border-radius: 999px;
      font-variant-numeric: tabular-nums;
      font-size: 12.5px; font-weight: 600; letter-spacing: .01em;
      border: 1px solid transparent; white-space: nowrap;
    }
    .liquidity::before {
      content: ""; width: 6px; height: 6px; border-radius: 999px;
    }
    .liq-high    { background: rgba(86,216,154,.14); color: #b9f8d7; border-color: rgba(86,216,154,.34); }
    .liq-high::before    { background: var(--green); box-shadow: 0 0 8px var(--green); }
    .liq-medium  { background: rgba(245,179,66,.14); color: #ffd58a; border-color: rgba(245,179,66,.32); }
    .liq-medium::before  { background: var(--gold); }
    .liq-low     { background: rgba(255,107,107,.10); color: #ffc1c1; border-color: rgba(255,107,107,.28); }
    .liq-low::before     { background: var(--red); }
    .liq-zero    { background: rgba(255,255,255,.05); color: var(--muted); border-color: rgba(255,255,255,.10); }
    .liq-zero::before    { background: var(--muted); }
    .liq-unknown { background: rgba(121,169,255,.10); color: #c8dcff; border-color: rgba(121,169,255,.28); }
    .liq-unknown::before { background: var(--blue); }
    .source-health {
      margin-top: 24px; padding: 22px; display: grid;
      grid-template-columns: 1fr; gap: 18px;
    }
    .source-health h2 { margin: 0; font-size: 18px; }
    .health-grid {
      display: grid; gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }
    .health-item {
      padding: 12px 14px; border-radius: 10px;
      background: rgba(7, 10, 16, .48);
      border: 1px solid var(--line);
    }
    .health-item span { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }
    .health-item strong { display: block; margin-top: 4px; font-size: 18px; font-variant-numeric: tabular-nums; }
    .health-warning {
      padding: 12px 14px; border-radius: 10px;
      background: rgba(245,179,66,.10);
      border: 1px solid rgba(245,179,66,.32);
      color: #ffd58a; font-size: 13px; line-height: 1.55;
    }
    .detail-actions { margin-top: 14px; }
    .buff-link {
      display: inline-flex; align-items: center; gap: 6px;
      min-height: 38px; padding: 8px 14px;
      border-radius: 10px; text-decoration: none;
      background: linear-gradient(135deg, var(--gold), var(--orange));
      color: #1a1004; font-weight: 700; font-size: 14px;
      transition: transform .18s ease, box-shadow .18s ease;
    }
    .buff-link:hover { transform: translateY(-2px); box-shadow: 0 10px 28px rgba(245,179,66,.28); }
    .listing-monitor-grid {
      display: grid; gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      margin-top: 14px;
    }
    .lm-card {
      padding: 14px; border-radius: 12px;
      background: rgba(7,10,16,.55);
      border: 1px solid var(--line);
      display: flex; flex-direction: column; gap: 6px;
    }
    .lm-card .panel-kicker { margin: 0; }
    .lm-card strong { font-size: 15px; line-height: 1.3; color: var(--text); }
    .lm-card span.muted { font-size: 12.5px; }
    .lm-card .pricepill {
      align-self: flex-start; margin-top: 4px;
      font-variant-numeric: tabular-nums; font-size: 13px;
      padding: 3px 8px; border-radius: 999px;
      background: rgba(245,179,66,.12); color: #ffd58a;
      border: 1px solid rgba(245,179,66,.24);
    }
    .family-grid {
      display: grid; gap: 12px; margin-top: 12px;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    }
    .fam-card {
      padding: 14px; border-radius: 12px;
      background: rgba(7,10,16,.55);
      border: 1px solid var(--line);
      display: flex; flex-direction: column; gap: 8px;
      cursor: pointer; transition: transform .18s ease, border-color .18s ease;
    }
    .fam-card:hover { transform: translateY(-2px); border-color: var(--line-strong); }
    .fam-card .fam-head { display: flex; align-items: center; gap: 10px; }
    .fam-card img { width: 42px; height: 32px; object-fit: contain; }
    .fam-card .fam-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; font-size: 12.5px; color: var(--muted); }
    .fam-card .fam-meta strong { color: var(--text); font-variant-numeric: tabular-nums; }
    #familyBrowser { display: none; }
    #familyBrowser.open { display: block; }
    #skinSearch { width: 100%; min-height: 40px; padding: 0 12px; border-radius: 10px; background: rgba(7,10,16,.6); border: 1px solid var(--line); color: var(--text); }
    .skin-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); max-height: 460px; overflow-y: auto; padding-right: 4px; }
    .skin-pick {
      display: flex; gap: 10px; align-items: center; text-align: left;
      padding: 10px; border-radius: 12px;
      background: rgba(7,10,16,.55); border: 1px solid var(--line);
    }
    .skin-pick:hover { border-color: var(--line-strong); transform: translateY(-2px); }
    .skin-pick.selected-row { border-color: var(--gold); background: rgba(245,179,66,.10); }
    .skin-pick img { width: 54px; height: 40px; object-fit: contain; flex: 0 0 auto; }
    .skin-pick .sp-body { min-width: 0; }
    .skin-pick strong { display: block; font-size: 13px; line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .skin-pick span { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
    .wear-ladder { display: flex; flex-direction: column; gap: 6px; }
    .wl-row { display: grid; grid-template-columns: 42px 1fr auto; gap: 10px; align-items: center; }
    .wl-row .wl-wear { font-weight: 700; font-size: 12px; color: var(--muted); }
    .wl-row.active .wl-wear { color: var(--gold); }
    .wl-bar { height: 10px; border-radius: 999px; background: rgba(255,255,255,.06); overflow: hidden; }
    .wl-bar > i { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--gold), var(--orange)); }
    .wl-row .wl-price { font-variant-numeric: tabular-nums; font-size: 12.5px; }
    .wl-row.missing .wl-price { color: var(--muted); }
    .range-toggle { display: inline-flex; gap: 4px; background: rgba(7,10,16,.6); border: 1px solid var(--line); border-radius: 10px; padding: 3px; }
    .range-toggle button { min-height: 30px; padding: 4px 12px; border-radius: 8px; border: none; background: transparent; color: var(--muted); font-size: 12.5px; font-weight: 600; }
    .range-toggle button.active { background: linear-gradient(135deg, var(--gold), var(--orange)); color: #1a1004; }
    .chart-meta { display: flex; justify-content: space-between; gap: 12px; margin-top: 8px; color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
    .ph-svg { width: 100%; height: 100%; display: block; }
    .ph-area { fill: url(#phArea); }
    .ph-line { fill: none; stroke: url(#phLine); stroke-width: 2; }
    .ph-grid { stroke: rgba(255,255,255,.06); stroke-width: 1; }
    .ph-axis { fill: var(--muted); font-size: 11px; }
    .ph-crosshair { stroke: var(--gold); stroke-width: 1; stroke-dasharray: 3 3; opacity: 0; }
    .ph-dot { fill: var(--gold); opacity: 0; }
    .ph-tip {
      position: absolute; pointer-events: none; opacity: 0;
      background: rgba(7,10,16,.95); border: 1px solid var(--line-strong);
      border-radius: 8px; padding: 6px 10px; font-size: 12px; color: var(--text);
      transform: translate(-50%, -120%); white-space: nowrap; z-index: 5;
      font-variant-numeric: tabular-nums;
    }
    .ph-tip b { color: var(--gold); }
    .mobile-cards { display: none; grid-template-columns: 1fr; gap: 10px; }
    .mc-card {
      display: grid; grid-template-columns: 60px 1fr auto; gap: 10px;
      align-items: center; padding: 10px;
      border: 1px solid var(--line); border-radius: 12px;
      background: rgba(7,10,16,.55); cursor: pointer;
    }
    .mc-card:hover, .mc-card.selected-row { border-color: var(--gold); }
    .mc-card img { width: 60px; height: 44px; object-fit: contain; }
    .mc-card .mc-body { min-width: 0; }
    .mc-card .mc-name { font-weight: 700; font-size: 13.5px; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
    .mc-card .mc-meta { font-size: 11.5px; color: var(--muted); margin-top: 2px; font-variant-numeric: tabular-nums; }
    .mc-card .mc-price { text-align: right; }
    .mc-card .mc-price strong { display: block; font-size: 14px; font-variant-numeric: tabular-nums; }
    .mc-card .mc-price span { font-size: 11px; }
    @media (max-width: 768px) {
      .table-shell { display: none; }
      .mobile-cards { display: grid; }
      .table-tools { grid-template-columns: 1fr 1fr; }
      .table-tools input { grid-column: span 2; }
      .table-tools .reset-btn { grid-column: span 2; }
    }
    .table-actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 16px; color: var(--muted); font-size: 12px; }
    .load-more {
      min-height: 38px;
      border-radius: 10px;
      padding: 8px 12px;
      color: #ffd58a;
    }
    .muted { color: var(--muted); }
    .visually-hidden {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        scroll-behavior: auto !important;
        transition-duration: .01ms !important;
        animation-duration: .01ms !important;
      }
    }
    @media (max-width: 920px) {
      main { width: min(100% - 22px, 1240px); padding-top: 18px; }
      .hero { padding: 22px; }
      .hero-grid, .layout { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .coverage { grid-template-columns: 1fr; }
      .item-detail { grid-template-columns: 1fr; }
      .knife-atlas { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .related-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .table-tools { grid-template-columns: 1fr; }
    }
    @media (max-width: 560px) {
      .topbar { align-items: flex-start; flex-direction: column; }
      .metrics { grid-template-columns: 1fr; }
      .hero-card strong { font-size: 28px; }
      .chart-wrap { height: 230px; }
      .knife-atlas { grid-template-columns: 1fr; }
      .related-grid { grid-template-columns: 1fr; }
      .detail-meta, .wear-row, .detail-prices { flex-direction: column; }
    }
  </style>
</head>
<body>
<main>
  <div class="topbar">
    <div class="brand"><div class="mark">B</div><div>BUFF163 Intelligence</div></div>
    <div><span class="badge live"><span class="dot"></span> Updated __UPDATED_AT__ UTC</span></div>
  </div>
  <section class="hero">
    <div class="hero-grid">
      <div>
        <div class="badge-row">
          <span class="badge live"><span class="dot"></span> Daily Lambda refresh</span>
          <span class="badge">S3 + CloudFront static</span>
          <span class="badge">Cost-safe mode</span>
        </div>
        <h1>Find underpriced CS2 knives faster with BUFF163 price, listing, and liquidity signals.</h1>
        <p class="subtitle">Track item-level prices, spread, supply, and market movement from a static edge dashboard. No database, no always-on backend, no surprise bill.</p>
      </div>
      <div class="hero-card">
        <span>Knife coverage</span>
        <strong>__COUNT__ rows</strong>
        <p>__KNIFE_FAMILY_COUNT__ knife families tracked. Top concentration: __TOP_KNIFE_TYPE__. Prices are normalized to CNY from the public BUFF163 market feed.</p>
      </div>
    </div>
  </section>

  <section class="metrics" aria-label="Market KPIs">
    <div class="metric">
      <div class="metric-head"><span>Tracked skins</span><div class="icon">__ICON_LAYERS__</div></div>
      <strong>__COUNT__</strong><div class="trend up">Static dataset loaded</div>
    </div>
    <div class="metric">
      <div class="metric-head"><span>Knife families</span><div class="icon">__ICON_KNIFE__</div></div>
      <strong>__KNIFE_FAMILY_COUNT__</strong><div class="trend up">Full knife list indexed</div>
    </div>
    <div class="metric">
      <div class="metric-head"><span>Average price</span><div class="icon">__ICON_CHART__</div></div>
      <strong>__AVG_PRICE__ CNY</strong><div class="trend warn">Across selected knife markets</div>
    </div>
    <div class="metric">
      <div class="metric-head"><span>Premium range</span><div class="icon">__ICON_FLASH__</div></div>
      <strong>__HIGH_PRICE__ CNY</strong><div class="trend">Low __LOW_PRICE__ CNY</div>
    </div>
  </section>

  <section class="panel" style="margin-top:16px" aria-label="Knife families">
    <div class="panel-title"><div><span class="panel-kicker">All knife list</span><h2>Browse by knife family</h2></div><span class="badge" id="familyCount">0 families</span></div>
    <div class="family-rail" id="knifeRail"></div>
    <div class="family-grid" id="familyCards" style="margin-top:14px"></div>
  </section>

  <section class="panel" style="margin-top:16px" id="familyBrowser" aria-label="Skins in selected family">
    <div class="panel-title"><div><span class="panel-kicker">Pick a skin</span><h2 id="familyBrowserTitle">Skins</h2></div><span class="badge" id="familyBrowserCount">0 skins</span></div>
    <input id="skinSearch" placeholder="Filter skins in this family" style="margin-bottom:12px">
    <div class="skin-grid" id="skinGrid"></div>
  </section>

  <section class="panel item-detail" aria-label="Selected item detail">
    <div class="detail-media">
      <img class="detail-art" id="detailImage" src="__INITIAL_DETAIL_IMAGE__" alt="__INITIAL_DETAIL_NAME__ image">
    </div>
    <div class="detail-content">
      <div class="detail-title">
        <span class="panel-kicker">Buff.163 item detail</span>
        <h2 id="detailName">__INITIAL_DETAIL_NAME__</h2>
      </div>
      <div class="detail-meta">
        <span class="badge">Quality <strong id="detailQuality">__INITIAL_DETAIL_QUALITY__</strong></span>
        <span class="badge">Category <strong id="detailCategory">__INITIAL_DETAIL_CATEGORY__</strong></span>
        <span class="badge">Type <strong id="detailType">__INITIAL_DETAIL_TYPE__</strong></span>
      </div>
      <div class="detail-prices">
        <div class="price-tile"><span>Latest price</span><strong id="detailLatestPrice">__INITIAL_DETAIL_PRICE__</strong></div>
        <div class="price-tile"><span>Reference price</span><strong id="detailReferencePrice">__INITIAL_DETAIL_REF__</strong></div>
        <div class="price-tile"><span>Spread</span><strong id="detailSpread">__INITIAL_DETAIL_SPREAD__</strong></div>
        <div class="price-tile"><span>Listings (Sell)</span><strong id="detailListings">N/A</strong></div>
      </div>
      <div class="detail-actions">
        <a id="detailBuffLink" class="buff-link" href="__INITIAL_BUFF_SEARCH__" target="_blank" rel="noopener noreferrer">Search on BUFF163 &rarr;</a>
      </div>
      <div>
        <span class="panel-kicker">Wear</span>
        <div class="wear-row" id="wearButtons"></div>
      </div>
      <div style="margin-top:14px">
        <span class="panel-kicker">How wear affects this skin</span>
        <div class="wear-ladder" id="wearLadder"></div>
      </div>
    </div>
  </section>

  <section class="panel" style="margin-top:16px">
    <div class="panel-title">
      <div><span class="panel-kicker">Price history</span><h2 id="priceChartTitle">Selected item price history</h2></div>
      <div class="range-toggle" id="rangeToggle">
        <button type="button" data-days="7">7D</button>
        <button type="button" data-days="30">30D</button>
        <button type="button" data-days="90" class="active">90D</button>
        <button type="button" data-days="365">1Y</button>
      </div>
    </div>
    <div id="priceChart" class="chart-wrap"></div>
    <div class="chart-meta" id="priceChartMeta"></div>
  </section>

  <section class="panel" style="margin-top:16px" aria-label="Supply vs price">
    <div class="panel-title">
      <div><span class="panel-kicker">Supply vs price</span><h2>How listing count affects price</h2></div>
      <span class="badge" id="supplyBadge">0 items</span>
    </div>
    <div id="supplyChart" class="chart-wrap" style="height:360px;position:relative"></div>
    <div class="chart-meta" id="supplyMeta"></div>
  </section>

  <section class="panel" style="margin-top:16px">
    <div class="panel-title"><div><span class="panel-kicker">Related items</span><h2>Same category</h2></div><span class="badge" id="relatedCount">0 items</span></div>
    <div class="related-grid" id="relatedItems"></div>
  </section>

  <section class="layout">
    <aside class="panel">
      <div class="panel-title"><div><span class="panel-kicker">Market insights</span><h2>Signal summary</h2></div></div>
      <div class="insight-list" id="insights"></div>
    </aside>
    <aside class="panel">
      <div class="panel-title"><div><span class="panel-kicker">Source health</span><h2>Free-tier runtime</h2></div></div>
      <p>This dashboard is generated by a scheduled Lambda and served as static files from S3 through CloudFront. It stays frontend-only in the browser and does not require a running backend.</p>
      <div class="insight-list">
        <div class="insight"><strong>Refresh cadence</strong><span class="muted">Daily scheduled scrape. Manual refresh can invoke the Lambda.</span></div>
        <div class="insight"><strong>Cost profile</strong><span class="muted">No NAT, RDS, App Runner, ECS, ALB, or ECR in this mode.</span></div>
      </div>
    </aside>
  </section>

  <section class="panel" style="margin-top:16px" aria-label="Market signals">
    <div class="panel-title"><div><span class="panel-kicker">Market signals</span><h2>Price highlights</h2></div></div>
    <div class="listing-monitor-grid" id="listingMonitor"></div>
  </section>

  <section class="panel source-health" id="sourceHealth">
    <div class="panel-title"><div><span class="panel-kicker">Data quality</span><h2>Dataset coverage</h2></div><span class="badge" id="healthBadge">Loading</span></div>
    <div class="health-grid" id="healthGrid"></div>
    <div class="health-warning" id="healthWarning" hidden></div>
  </section>

  <section class="panel" style="margin-top:16px">
    <div class="panel-title"><div><span class="panel-kicker">Tracked skins</span><h2>Market table</h2></div><span class="badge" id="tableCount">0 rows</span></div>
    <div class="table-tools">
      <label class="visually-hidden" for="search">Search skin, knife, condition</label>
      <input id="search" placeholder="Search skin, knife, condition">
      <label class="visually-hidden" for="knifeType">Knife family</label>
      <select id="knifeType"><option value="">All knife families</option></select>
      <label class="visually-hidden" for="condition">Condition</label>
      <select id="condition"><option value="">All conditions</option></select>
      <label class="visually-hidden" for="sort">Sort</label>
      <select id="sort">
        <option value="price-desc">Price high to low</option>
        <option value="price-asc">Price low to high</option>
        <option value="listings-desc">Listings high to low</option>
        <option value="spread-desc">Spread high to low</option>
        <option value="spread-asc">Spread low to high</option>
        <option value="name">Name A-Z</option>
        <option value="family">Family A-Z</option>
      </select>
      <button class="reset-btn" id="resetFilters" type="button">Reset</button>
    </div>
    <div class="table-shell">
      <table>
        <thead><tr><th>Item</th><th>Wear</th><th class="right">Price</th><th class="right">Reference</th><th>Spread</th><th class="right">Listings</th><th>Source</th></tr></thead>
        <tbody id="rows">__INITIAL_TABLE_ROWS__</tbody>
      </table>
    </div>
    <div class="mobile-cards" id="mobileCards"></div>
    <div class="table-actions">
      <span id="tableNote">Showing matching rows.</span>
      <button class="load-more" id="loadMore" type="button">Load more</button>
    </div>
  </section>
</main>
<script>
const rows = __ROWS_JSON__;
const knifeTypes = __KNIFE_TYPES_JSON__;
const tbody = document.getElementById("rows");
const search = document.getElementById("search");
const knifeType = document.getElementById("knifeType");
const condition = document.getElementById("condition");
const sort = document.getElementById("sort");
const tableCount = document.getElementById("tableCount");
const tableNote = document.getElementById("tableNote");
const loadMore = document.getElementById("loadMore");
const knifeRail = document.getElementById("knifeRail");
const detailImage = document.getElementById("detailImage");
const detailName = document.getElementById("detailName");
const detailQuality = document.getElementById("detailQuality");
const detailCategory = document.getElementById("detailCategory");
const detailType = document.getElementById("detailType");
const detailLatestPrice = document.getElementById("detailLatestPrice");
const detailReferencePrice = document.getElementById("detailReferencePrice");
const detailSpread = document.getElementById("detailSpread");
const detailListings = document.getElementById("detailListings");
const wearButtons = document.getElementById("wearButtons");
// Inline gradient SVG used whenever a Steam CDN image 404s or is missing.
const FALLBACK_IMG = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 120"><defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#f5b342"/><stop offset=".55" stop-color="#ff7a1a"/><stop offset="1" stop-color="#111827"/></linearGradient></defs><rect width="160" height="120" rx="14" fill="#0b101a"/><path d="M119 21 139 41 70 110 45 115 50 90Z" fill="url(#g)"/><path d="M47 82 78 113" stroke="#f8d08a" stroke-width="7" stroke-linecap="round"/></svg>');
function imgFallback(el) { el.onerror = null; el.src = FALLBACK_IMG; }
const detailBuffLink = document.getElementById("detailBuffLink");
const relatedItems = document.getElementById("relatedItems");
const relatedCount = document.getElementById("relatedCount");
const imageByKnife = Object.fromEntries(knifeTypes.map(item => [item.name, item.image_url]));
const wearLadder = document.getElementById("wearLadder");
const familyBrowser = document.getElementById("familyBrowser");
const familyBrowserTitle = document.getElementById("familyBrowserTitle");
const familyBrowserCount = document.getElementById("familyBrowserCount");
const skinGrid = document.getElementById("skinGrid");
const skinSearch = document.getElementById("skinSearch");
const priceChartTitle = document.getElementById("priceChartTitle");
const priceChartMeta = document.getElementById("priceChartMeta");
const rangeToggle = document.getElementById("rangeToggle");
let tableLimit = 300;
let selectedRow = [...rows].sort((a,b) => rowPrice(b) - rowPrice(a))[0] || rows[0] || null;
let selectedFamily = "";
let rangeDays = 90;
let priceHistory = {};
const wearOrder = ["FN", "MW", "FT", "WW", "BS"];
function goodsIdOf(row) {
  const u = row && row.buff_url;
  if (!u) return null;
  const i = String(u).indexOf("/goods/");
  if (i < 0) return null;
  let out = "";
  for (const ch of String(u).slice(i + 7)) {
    if (ch >= "0" && ch <= "9") out += ch; else break;
  }
  return out || null;
}
// Load real BUFF price history (written by the cookie-enabled Lambda run).
fetch("current/price_history.json", {cache: "no-store"})
  .then(r => r.ok ? r.json() : {})
  .then(d => { priceHistory = d || {}; renderPriceChart(); })
  .catch(() => {});
function money(value) { return value == null ? "N/A" : Number(value).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + " CNY"; }
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}
function spread(row) {
  const price = rowPrice(row);
  const reference = Number(row.reference_price_cny);
  if (!Number.isFinite(reference) || price <= 0) return "N/A";
  const pct = ((price - reference) / price) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}
function unique(values) { return [...new Set(values)].sort((a,b) => String(a).localeCompare(String(b))); }
knifeType.innerHTML += knifeTypes.map(item => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)} (${item.count.toLocaleString()})</option>`).join("");
condition.innerHTML += unique(rows.map(row => row.condition)).map(value => `<option value="${value}">${value}</option>`).join("");
function imageForRow(row) { return row.image_url || imageByKnife[row.knife_type] || ""; }
function rowPrice(row) {
  const price = Number(row.price ?? row.price_cny ?? 0);
  return Number.isFinite(price) ? price : 0;
}
function spreadValue(row) {
  const v = Number(row.spread_percent);
  return Number.isFinite(v) ? v : null;
}
function spreadText(row) {
  const v = spreadValue(row);
  if (v === null) return spread(row);
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}
function listingValue(row) {
  const raw = row.listing_count;
  if (raw === null || raw === undefined) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}
function listingText(row) {
  const v = listingValue(row);
  return v === null ? "N/A" : v.toLocaleString();
}
const anyListings = rows.some(r => listingValue(r) !== null);
function selectedFamilyRows() {
  if (!selectedRow) return rows;
  const familyRows = rows.filter(row => row.family === selectedRow.family);
  return familyRows.length ? familyRows : [selectedRow];
}
function setKnifeFilter(value) {
  knifeType.value = value;
  selectedFamily = value;
  if (skinSearch) skinSearch.value = "";
  tableLimit = 300;
  const candidates = rows.filter(row => !value || row.knife_type === value);
  if (candidates.length) selectedRow = [...candidates].sort((a,b) => rowPrice(b) - rowPrice(a))[0];
  render();
  if (value) familyBrowser?.scrollIntoView({behavior: "smooth", block: "start"});
}
function selectRow(row) {
  selectedRow = row;
  knifeType.value = row.knife_type || "";
  render();
  document.querySelector(".item-detail")?.scrollIntoView({behavior: "smooth", block: "start"});
}
function renderFamilyBrowser() {
  if (!familyBrowser) return;
  if (!selectedFamily) { familyBrowser.classList.remove("open"); return; }
  familyBrowser.classList.add("open");
  familyBrowserTitle.textContent = selectedFamily;
  const q = (skinSearch?.value || "").toLowerCase();
  let pool = rows.filter(r => r.knife_type === selectedFamily);
  if (q) pool = pool.filter(r => `${r.item_name} ${r.skin_name} ${r.condition}`.toLowerCase().includes(q));
  pool.sort((a,b) => rowPrice(b) - rowPrice(a));
  familyBrowserCount.textContent = `${pool.length.toLocaleString()} skins`;
  if (!pool.length) {
    skinGrid.innerHTML = `<div class="empty-state"><div><strong>No skins</strong><p>No skins match in this family.</p></div></div>`;
    return;
  }
  skinGrid.innerHTML = pool.map(r => {
    const sel = selectedRow && r.goods_id === selectedRow.goods_id;
    return `<button class="skin-pick ${sel ? "selected-row" : ""}" type="button" data-id="${escapeHtml(r.goods_id)}">
      <img src="${escapeHtml(imageForRow(r) || FALLBACK_IMG)}" alt="" loading="lazy" onerror="imgFallback(this)">
      <div class="sp-body"><strong>${escapeHtml(r.skin_name || r.item_name)}</strong><span>${escapeHtml(r.wear || r.condition)} &middot; ${money(r.price ?? r.price_cny)}${listingValue(r) !== null ? " &middot; Sell " + listingText(r) : ""}</span></div>
    </button>`;
  }).join("");
  skinGrid.querySelectorAll("button").forEach(btn => {
    btn.addEventListener("click", () => {
      const m = rows.find(r => r.goods_id === btn.dataset.id);
      if (m) selectRow(m);
    });
  });
}
function renderWearLadder() {
  if (!wearLadder || !selectedRow) return;
  const sameSkin = rows.filter(r => r.item_name === selectedRow.item_name);
  const prices = sameSkin.map(rowPrice).filter(p => p > 0);
  const max = prices.length ? Math.max(...prices) : 1;
  wearLadder.innerHTML = wearOrder.map(w => {
    const m = sameSkin.find(r => r.wear === w);
    if (!m) return `<div class="wl-row missing"><span class="wl-wear">${w}</span><div class="wl-bar"></div><span class="wl-price">N/A</span></div>`;
    const p = rowPrice(m);
    const pct = Math.max((p / max) * 100, 3);
    const active = selectedRow.wear === w ? " active" : "";
    return `<div class="wl-row${active}" data-id="${escapeHtml(m.goods_id)}" style="cursor:pointer"><span class="wl-wear">${w}</span><div class="wl-bar"><i style="width:${pct}%"></i></div><span class="wl-price">${money(p)}</span></div>`;
  }).join("");
  wearLadder.querySelectorAll(".wl-row[data-id]").forEach(el => {
    el.addEventListener("click", () => {
      const m = rows.find(r => r.goods_id === el.dataset.id);
      if (m) selectRow(m);
    });
  });
}
function renderKnifeRail() {
  const active = knifeType.value;
  const total = rows.length.toLocaleString();
  const chips = [`<button class="family-chip ${active === "" ? "active" : ""}" type="button" data-knife=""><span>All knives</span><span class="chip-count">${total}</span></button>`]
    .concat(knifeTypes.map(item => `<button class="family-chip ${active === item.name ? "active" : ""}" type="button" data-knife="${escapeHtml(item.name)}"><img src="${escapeHtml(item.image_url)}" alt=""><span>${escapeHtml(item.name)}</span><span class="chip-count">${item.count.toLocaleString()}</span></button>`));
  knifeRail.innerHTML = chips.join("");
  knifeRail.querySelectorAll("button").forEach(button => {
    button.addEventListener("click", () => setKnifeFilter(button.dataset.knife || ""));
  });
}
function renderDetail() {
  if (!selectedRow) return;
  detailImage.onerror = () => imgFallback(detailImage);
  detailImage.src = imageForRow(selectedRow) || FALLBACK_IMG;
  detailImage.alt = `${selectedRow.skin_name || selectedRow.item_name} image`;
  detailName.textContent = selectedRow.skin_name || selectedRow.item_name || "Unknown item";
  detailQuality.textContent = selectedRow.wear || selectedRow.condition || "N/A";
  detailCategory.textContent = selectedRow.condition || "N/A";
  detailType.textContent = selectedRow.knife_type || "N/A";
  detailLatestPrice.textContent = money(selectedRow.price ?? selectedRow.price_cny);
  detailReferencePrice.textContent = money(selectedRow.reference_price_cny);
  detailSpread.textContent = spreadText(selectedRow);
  if (detailListings) detailListings.textContent = listingText(selectedRow);
  if (detailBuffLink) {
    const q = encodeURIComponent(selectedRow.market_hash_name || selectedRow.item_name || "");
    detailBuffLink.href = selectedRow.buff_url || `https://buff.163.com/market/csgo#tab=selling&page_num=1&search=${q}`;
  }
  // Same-skin wear chips: lookup uses item_name so "Bayonet | Autotronic" only
  // jumps between its own wear variants, not other Bayonet skins.
  const sameSkin = rows.filter(row => row.item_name === selectedRow.item_name);
  wearButtons.innerHTML = wearOrder.map(wear => {
    const match = sameSkin.find(row => row.wear === wear);
    const active = selectedRow.wear === wear;
    return `<button class="wear-button ${active ? "active" : ""}" type="button" data-wear="${wear}" ${match ? "" : "disabled"}>${wear}</button>`;
  }).join("");
  wearButtons.querySelectorAll("button").forEach(button => {
    button.addEventListener("click", () => {
      const match = sameSkin.find(row => row.wear === button.dataset.wear);
      if (match) selectRow(match);
    });
  });
  renderWearLadder();
}
function filteredRows() {
  const q = search.value.toLowerCase();
  const selectedKnife = knifeType.value;
  const selectedCondition = condition.value;
  const filtered = rows.filter(row => {
    if (selectedKnife && row.knife_type !== selectedKnife) return false;
    if (selectedCondition && row.condition !== selectedCondition) return false;
    if (q && !`${row.skin_name} ${row.item_name} ${row.family} ${row.knife_type} ${row.condition}`.toLowerCase().includes(q)) return false;
    return true;
  });
  filtered.sort((a,b) => {
    const s = sort.value;
    if (s === "price-asc")    return rowPrice(a) - rowPrice(b);
    if (s === "listings-desc")return (listingValue(b) ?? -1) - (listingValue(a) ?? -1);
    if (s === "spread-desc")  return (Number(b.spread_percent)||-Infinity) - (Number(a.spread_percent)||-Infinity);
    if (s === "spread-asc")   return Math.abs(Number(a.spread_percent)||Infinity) - Math.abs(Number(b.spread_percent)||Infinity);
    if (s === "name")         return String(a.skin_name||"").localeCompare(String(b.skin_name||""));
    if (s === "family")       return String(a.family||"").localeCompare(String(b.family||"")) || rowPrice(b) - rowPrice(a);
    return rowPrice(b) - rowPrice(a);
  });
  return filtered;
}
function renderTable() {
  const filtered = filteredRows();
  const visible = filtered.slice(0, tableLimit);
  tableCount.textContent = `${filtered.length.toLocaleString()} rows`;
  tableNote.textContent = `Showing ${visible.length.toLocaleString()} of ${filtered.length.toLocaleString()} matching knife rows.`;
  loadMore.hidden = visible.length >= filtered.length;
  // Mobile cards (mirror of the table for narrow viewports).
  const mc = document.getElementById("mobileCards");
  if (mc) {
    mc.innerHTML = visible.map(row => {
      const sel = selectedRow && row.goods_id === selectedRow.goods_id;
      return `<div class="mc-card ${sel ? "selected-row" : ""}" data-id="${escapeHtml(row.goods_id)}">
        <img src="${escapeHtml(imageForRow(row) || FALLBACK_IMG)}" alt="" loading="lazy" onerror="imgFallback(this)">
        <div class="mc-body">
          <div class="mc-name">${escapeHtml(row.item_name || row.skin_name)}</div>
          <div class="mc-meta">${escapeHtml(row.wear || row.condition)} &middot; ${escapeHtml(row.knife_type || "")}${listingValue(row) !== null ? " &middot; Sell " + listingText(row) : ""}</div>
        </div>
        <div class="mc-price"><strong>${money(row.price ?? row.price_cny)}</strong><span>${spreadText(row)}</span></div>
      </div>`;
    }).join("");
    mc.querySelectorAll(".mc-card").forEach(el => {
      el.addEventListener("click", () => {
        const m = rows.find(r => r.goods_id === el.dataset.id);
        if (m) selectRow(m);
      });
    });
  }
  tbody.innerHTML = visible.map(row => {
    const isSelected = selectedRow && row.goods_id === selectedRow.goods_id;
    return `<tr data-id="${escapeHtml(row.goods_id)}" class="${isSelected ? "selected-row" : ""}"><td><div class="skin-cell"><img class="skin-thumb" src="${escapeHtml(imageForRow(row) || FALLBACK_IMG)}" alt="" loading="lazy" onerror="imgFallback(this)"><div><strong>${escapeHtml(row.item_name || row.skin_name)}</strong><small>${escapeHtml(row.knife_type || "Unknown")} &middot; ${escapeHtml(row.condition || "N/A")}</small></div></div></td><td><span class="pill">${escapeHtml(row.wear || row.condition || "N/A")}</span></td><td class="right">${money(row.price ?? row.price_cny)}</td><td class="right">${money(row.reference_price_cny)}</td><td>${spreadText(row)}</td><td class="right">${listingText(row)}</td><td>${escapeHtml(row.source)}</td></tr>`;
  }).join("");
  tbody.querySelectorAll("tr").forEach(rowEl => {
    rowEl.addEventListener("click", () => {
      const match = rows.find(row => row.goods_id === rowEl.dataset.id);
      if (match) selectRow(match);
    });
  });
}
function _fmtDate(ms) {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
function seriesPair(gid) {
  // Normalises both legacy ([[ts,p],...]) and new ({listing:[],buy_order:[]})
  // shapes of priceHistory entries to {listing, buy_order}. Returns null when
  // there's no usable data for the goods_id.
  const raw = gid ? priceHistory[gid] : null;
  if (!raw) return null;
  if (Array.isArray(raw)) return { listing: raw, buy_order: [] };
  return { listing: raw.listing || [], buy_order: raw.buy_order || [] };
}
function renderPriceChart() {
  const host = document.getElementById("priceChart");
  if (!host) return;
  const gid = goodsIdOf(selectedRow);
  const pair = seriesPair(gid);
  if (pair && pair.listing.length >= 2) {
    if (priceChartTitle) priceChartTitle.textContent = `${selectedRow.skin_name || selectedRow.item_name} — BUFF price history`;
    renderTimeSeries(host, pair);
    return;
  }
  // Fallback: pick nearest item in the same family that DOES have BUFF history,
  // by absolute price distance. Renders that real time-series instead of an
  // empty placeholder so the chart panel is always populated when any data
  // for the family exists.
  const target = rowPrice(selectedRow);
  const familyHistoryItems = rows
    .filter(r => r.family === selectedRow.family && goodsIdOf(r) && priceHistory[goodsIdOf(r)])
    .sort((a, b) => Math.abs(rowPrice(a) - target) - Math.abs(rowPrice(b) - target));
  if (familyHistoryItems.length) {
    const proxy = familyHistoryItems[0];
    const proxyPair = seriesPair(goodsIdOf(proxy));
    if (priceChartTitle) priceChartTitle.textContent = `${proxy.skin_name || proxy.item_name} — BUFF price history`;
    renderTimeSeries(host, proxyPair);
    if (priceChartMeta) {
      const note = `Showing closest ${selectedRow.family} item with BUFF history (${proxy.skin_name || proxy.item_name}). Real history for "${selectedRow.skin_name || selectedRow.item_name}" not yet fetched.`;
      const existing = priceChartMeta.innerHTML;
      priceChartMeta.innerHTML = existing + `<span class="muted" style="display:block;margin-top:4px;font-size:11.5px">${escapeHtml(note)}</span>`;
    }
    return;
  }
  // No family proxy. Last resort: show ANY available BUFF series so the panel
  // is never empty. Pick by closest price across all rows with history.
  const anyHistoryItems = rows
    .filter(r => goodsIdOf(r) && priceHistory[goodsIdOf(r)])
    .sort((a, b) => Math.abs(rowPrice(a) - target) - Math.abs(rowPrice(b) - target));
  if (anyHistoryItems.length) {
    const proxy = anyHistoryItems[0];
    const proxyPair = seriesPair(goodsIdOf(proxy));
    if (priceChartTitle) priceChartTitle.textContent = `${proxy.skin_name || proxy.item_name} — BUFF price history (proxy)`;
    renderTimeSeries(host, proxyPair);
    if (priceChartMeta) {
      priceChartMeta.innerHTML += `<span class="muted" style="display:block;margin-top:4px;font-size:11.5px">No BUFF history yet for ${escapeHtml(selectedRow.skin_name || selectedRow.item_name)}. Showing closest-price item with data: ${escapeHtml(proxy.skin_name)}.</span>`;
    }
    return;
  }
  // True empty state — no history fetched at all.
  if (priceChartTitle) priceChartTitle.textContent = `${selectedRow.skin_name || selectedRow.item_name} — price history pending`;
  if (priceChartMeta) priceChartMeta.textContent = "";
  host.innerHTML = `<div class="empty-state"><div><strong>BUFF price history not yet fetched.</strong><p>Current price: ${money(rowPrice(selectedRow||{}))}. Real time-series appears once the scheduled Lambda fetches BUFF history with a valid cookie.</p></div></div>`;
}
function _filterRange(arr) {
  const cutoff = Date.now() - rangeDays * 86400000;
  let s = arr.filter(p => p[0] >= cutoff);
  if (s.length < 2) s = arr.slice(-Math.max(2, Math.min(arr.length, rangeDays)));
  return s;
}
function renderTimeSeries(host, pair) {
  // Back-compat: accept either {listing,buy_order} or a bare array.
  if (Array.isArray(pair)) pair = { listing: pair, buy_order: [] };
  const series = _filterRange(pair.listing || []);
  const buy = _filterRange(pair.buy_order || []);
  const w = 900, h = 280, padL = 60, padR = 16, padT = 16, padB = 26;
  // X domain spans both series so they share the same axis.
  const xs = series.map(p => p[0]).concat(buy.map(p => p[0]));
  const ys = series.map(p => p[1]).concat(buy.map(p => p[1]));
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const X = t => padL + ((t - minX) / Math.max(maxX - minX, 1)) * (w - padL - padR);
  const Y = v => h - padB - ((v - minY) / Math.max(maxY - minY, 1)) * (h - padT - padB);
  const linePts = series.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(" ");
  const areaPts = `${padL},${h-padB} ${linePts} ${(w-padR)},${h-padB}`;
  const buyPts = buy.length ? buy.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(" ") : "";
  // horizontal gridlines + y labels (4 ticks)
  let grid = "";
  for (let i = 0; i <= 4; i++) {
    const val = minY + (maxY - minY) * (i / 4);
    const yy = Y(val);
    grid += `<line class="ph-grid" x1="${padL}" y1="${yy}" x2="${w-padR}" y2="${yy}"></line>`;
    grid += `<text class="ph-axis" x="8" y="${yy+4}">${Math.round(val).toLocaleString()}</text>`;
  }
  // x date labels (start / mid / end)
  let xlabels = "";
  [0, Math.floor(series.length/2), series.length-1].forEach(idx => {
    const p = series[idx];
    xlabels += `<text class="ph-axis" text-anchor="middle" x="${X(p[0])}" y="${h-8}">${_fmtDate(p[0])}</text>`;
  });
  // BUFF buff_price_type=1 returns transaction events (individual sales) —
  // spiky pattern matching the yellow line on BUFF's own price-chart UI.
  const buyLine = buyPts
    ? `<polyline points="${buyPts}" fill="none" stroke="#facc15" stroke-width="1.5" opacity="0.85"></polyline>`
    : "";
  const legend = `
    <div style="position:absolute;top:6px;right:10px;display:flex;gap:14px;font-size:12px;color:var(--muted);background:rgba(7,10,16,.6);padding:4px 10px;border-radius:8px;border:1px solid var(--line)">
      <span style="display:inline-flex;align-items:center;gap:5px"><span style="width:14px;height:2px;background:linear-gradient(90deg,#f5b342,#ff7a1a)"></span>Listing price</span>
      ${buyPts ? '<span style="display:inline-flex;align-items:center;gap:5px"><span style="width:14px;height:2px;background:#facc15"></span>Transactions</span>' : ""}
    </div>`;
  host.innerHTML = `
    <div style="position:relative;width:100%;height:100%">
      ${legend}
      <svg class="ph-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Price history">
        <defs>
          <linearGradient id="phLine" x1="0" x2="1"><stop stop-color="#f5b342"/><stop offset="1" stop-color="#ff7a1a"/></linearGradient>
          <linearGradient id="phArea" x1="0" x2="0" y1="0" y2="1"><stop stop-color="#f5b342" stop-opacity=".30"/><stop offset="1" stop-color="#f5b342" stop-opacity="0"/></linearGradient>
        </defs>
        ${grid}
        <polygon class="ph-area" points="${areaPts}"></polygon>
        ${buyLine}
        <polyline class="ph-line" points="${linePts}"></polyline>
        <line class="ph-crosshair" id="phCross" y1="${padT}" y2="${h-padB}"></line>
        <circle class="ph-dot" id="phDot" r="3.5"></circle>
        ${xlabels}
      </svg>
      <div class="ph-tip" id="phTip"></div>
    </div>`;
  if (priceChartMeta) {
    const first = series[0], last = series[series.length-1];
    const chg = first[1] ? ((last[1]-first[1])/first[1]*100) : 0;
    priceChartMeta.innerHTML = `<span>${_fmtDate(minX)} → ${_fmtDate(maxX)} &middot; ${series.length} points</span><span>Range ${money(minY)} – ${money(maxY)} &middot; <b style="color:${chg>=0?'var(--green)':'var(--red)'}">${chg>=0?'+':''}${chg.toFixed(1)}%</b></span>`;
  }
  // hover tooltip
  const svg = host.querySelector(".ph-svg");
  const tip = host.querySelector("#phTip");
  const cross = host.querySelector("#phCross");
  const dot = host.querySelector("#phDot");
  function _nearest(arr, px) {
    let best = arr[0], bestd = Infinity;
    for (const p of arr) { const d = Math.abs(X(p[0]) - px); if (d < bestd) { bestd = d; best = p; } }
    return best;
  }
  function onMove(ev) {
    const rect = svg.getBoundingClientRect();
    const px = (ev.clientX - rect.left) / rect.width * w;
    const listingBest = _nearest(series, px);
    const buyBest = buy.length ? _nearest(buy, px) : null;
    const cx = X(listingBest[0]), cy = Y(listingBest[1]);
    cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.style.opacity = 1;
    dot.setAttribute("cx", cx); dot.setAttribute("cy", cy); dot.style.opacity = 1;
    tip.style.opacity = 1;
    tip.style.left = (cx / w * rect.width) + "px";
    tip.style.top = (cy / h * rect.height) + "px";
    const buyLineHtml = buyBest
      ? `<br><span style="color:#facc15">Transaction ${money(buyBest[1])}</span>`
      : "";
    tip.innerHTML = `<b>Listing ${money(listingBest[1])}</b>${buyLineHtml}<br><span class="muted">${_fmtDate(listingBest[0])}</span>`;
  }
  function onLeave() { cross.style.opacity = 0; dot.style.opacity = 0; tip.style.opacity = 0; }
  svg.addEventListener("mousemove", onMove);
  svg.addEventListener("mouseleave", onLeave);
}
function renderRelatedItems() {
  if (!selectedRow) return;
  // Ranking: 1) same skin (item_name) other wears, 2) same family (weapon),
  // 3) closest price. Drops the selected row itself.
  const sameSkin = rows.filter(r => r.item_name === selectedRow.item_name && r.goods_id !== selectedRow.goods_id);
  const sameFamily = rows.filter(r => r.family === selectedRow.family && r.item_name !== selectedRow.item_name);
  const target = rowPrice(selectedRow);
  sameFamily.sort((a, b) => Math.abs(rowPrice(a) - target) - Math.abs(rowPrice(b) - target));
  const related = [...sameSkin, ...sameFamily].slice(0, 12);
  relatedCount.textContent = related.length ? `${related.length.toLocaleString()} items` : "0 items";
  if (!related.length) {
    relatedItems.innerHTML = `<div class="empty-state"><div><strong>No related items</strong><p>No other items in this skin or family are present in the current dataset.</p></div></div>`;
    return;
  }
  relatedItems.innerHTML = related.map(row => {
    return `<button class="related-card" type="button" data-id="${escapeHtml(row.goods_id)}">
      <img src="${escapeHtml(imageForRow(row) || FALLBACK_IMG)}" alt="" loading="lazy" onerror="imgFallback(this)">
      <div><strong>${escapeHtml(row.skin_name || row.item_name)}</strong><span>${escapeHtml(row.wear || row.condition)} &middot; ${money(row.price ?? row.price_cny)}</span></div>
    </button>`;
  }).join("");
  relatedItems.querySelectorAll("button").forEach(button => {
    button.addEventListener("click", () => {
      const match = rows.find(row => row.goods_id === button.dataset.id);
      if (match) selectRow(match);
    });
  });
}
function renderInsights() {
  const host = document.getElementById("insights");
  const prices = rows.map(row => rowPrice(row)).filter(price => price >= 1);
  const avg = prices.reduce((sum, price) => sum + price, 0) / Math.max(prices.length, 1);
  const premium = rows.filter(row => rowPrice(row) >= avg).length;
  const top = [...rows].sort((a,b) => rowPrice(b) - rowPrice(a))[0];
  host.innerHTML = [
    `<div class="insight"><strong>Premium pressure</strong><span class="muted">${premium.toLocaleString()} skins price above the market average.</span></div>`,
    `<div class="insight"><strong>Highest tracked skin</strong><span class="muted">${top ? `${top.skin_name} at ${money(top.price ?? top.price_cny)}` : "No high point yet."}</span></div>`,
    `<div class="insight"><strong>Execution note</strong><span class="muted">Use the table filters for quick watchlist discovery. Current dataset is a daily static snapshot.</span></div>`
  ].join("");
}
function renderSourceHealth() {
  const host = document.getElementById("healthGrid");
  const warn = document.getElementById("healthWarning");
  const badge = document.getElementById("healthBadge");
  if (!host) return;
  const total = rows.length;
  const withPrice = rows.filter(r => rowPrice(r) > 0).length;
  const withRef = rows.filter(r => Number.isFinite(Number(r.reference_price_cny))).length;
  const withSpread = rows.filter(r => spreadValue(r) !== null).length;
  const withImage = rows.filter(r => r.image_url).length;
  const withGoodsId = rows.filter(r => r.goods_id).length;
  const familiesCount = new Set(rows.map(r => r.knife_type).filter(Boolean)).size;
  const status = (withPrice === total && withImage === total) ? "Healthy" : "Partial";
  badge.textContent = status;
  badge.className = "badge " + (status === "Healthy" ? "live" : "");
  const items = [
    ["Total items", total.toLocaleString()],
    ["Items with price", withPrice.toLocaleString()],
    ["With reference price", withRef.toLocaleString()],
    ["With spread", withSpread.toLocaleString()],
    ["With image", withImage.toLocaleString()],
    ["With goods_id", withGoodsId.toLocaleString()],
    ["Knife families", familiesCount.toLocaleString()],
    ["Source", "csgotrader / BUFF163"],
  ];
  host.innerHTML = items.map(([k, v]) =>
    `<div class="health-item"><span>${escapeHtml(k)}</span><strong>${v}</strong></div>`
  ).join("");
  warn.hidden = true;
}
function renderFamilyCards() {
  const host = document.getElementById("familyCards");
  const badge = document.getElementById("familyCount");
  if (!host) return;
  const families = {};
  for (const r of rows) {
    const k = r.knife_type || "Unknown";
    (families[k] ||= { name: k, items: [] }).items.push(r);
  }
  const list = Object.values(families).sort((a, b) => b.items.length - a.items.length);
  badge.textContent = `${list.length.toLocaleString()} families`;
  host.innerHTML = list.map(f => {
    const prices = f.items.map(rowPrice).filter(p => p > 0);
    const avg = prices.length ? prices.reduce((s,p)=>s+p,0)/prices.length : 0;
    const mn = prices.length ? Math.min(...prices) : 0;
    const mx = prices.length ? Math.max(...prices) : 0;
    const img = imageByKnife[f.name] || (f.items.find(r => r.image_url)?.image_url) || "";
    return `<button class="fam-card" type="button" data-knife="${escapeHtml(f.name)}">
      <div class="fam-head"><img src="${escapeHtml(img || FALLBACK_IMG)}" alt="" loading="lazy" onerror="imgFallback(this)"><strong>${escapeHtml(f.name)}</strong></div>
      <div class="fam-meta">
        <span>Items <strong>${f.items.length.toLocaleString()}</strong></span>
        <span>Avg <strong>${money(avg)}</strong></span>
        <span>Min <strong>${money(mn)}</strong></span>
        <span>Max <strong>${money(mx)}</strong></span>
      </div>
    </button>`;
  }).join("");
  host.querySelectorAll("button").forEach(btn => {
    btn.addEventListener("click", () => setKnifeFilter(btn.dataset.knife || ""));
  });
}
function renderMarketSignals() {
  const host = document.getElementById("listingMonitor");
  if (!host) return;
  const byPrice = [...rows].sort((a,b) => rowPrice(b) - rowPrice(a));
  const top = byPrice[0];
  const cheap = byPrice.filter(r => rowPrice(r) > 0).pop();
  const withSpread = rows.filter(r => spreadValue(r) !== null);
  const biggestSpread = [...withSpread].sort((a,b) => (b.spread_percent||0) - (a.spread_percent||0))[0];
  const tightestSpread = [...withSpread].sort((a,b) => Math.abs(a.spread_percent||0) - Math.abs(b.spread_percent||0))[0];

  function card(kicker, row, hint) {
    if (!row) return `<div class="lm-card"><span class="panel-kicker">${escapeHtml(kicker)}</span><strong>No data</strong></div>`;
    return `<button class="lm-card" type="button" data-id="${escapeHtml(row.goods_id)}" style="text-align:left;cursor:pointer">
      <span class="panel-kicker">${escapeHtml(kicker)}</span>
      <strong>${escapeHtml(row.skin_name || row.item_name)}</strong>
      <span class="muted">${escapeHtml(hint)}</span>
      <span class="pricepill">${money(row.price_cny)} &middot; ${spreadText(row)}</span>
    </button>`;
  }

  host.innerHTML = [
    card("Highest tracked price", top, top ? `${top.knife_type} / ${top.wear}` : ""),
    card("Cheapest valid item", cheap, cheap ? `${cheap.knife_type} / ${cheap.wear}` : ""),
    card("Biggest spread vs reference", biggestSpread, biggestSpread ? `${biggestSpread.knife_type} / ${biggestSpread.wear}` : ""),
    card("Tightest spread", tightestSpread, tightestSpread ? `${tightestSpread.knife_type} / ${tightestSpread.wear}` : ""),
  ].join("");
  host.querySelectorAll("button.lm-card").forEach(btn => {
    btn.addEventListener("click", () => {
      const m = rows.find(r => r.goods_id === btn.dataset.id);
      if (m) selectRow(m);
    });
  });
}
function renderSupplyChart() {
  const host = document.getElementById("supplyChart");
  const badge = document.getElementById("supplyBadge");
  const meta = document.getElementById("supplyMeta");
  if (!host) return;
  const enriched = rows.filter(r => listingValue(r) !== null && listingValue(r) > 0 && rowPrice(r) > 0);
  badge.textContent = `${enriched.length.toLocaleString()} items`;
  if (enriched.length < 3) {
    host.innerHTML = `<div class="empty-state"><div><strong>Not enough listing data yet</strong><p>Once BUFF Sell(N) counts are fetched for more items, this chart shows how supply relates to price across all listed knives.</p></div></div>`;
    if (meta) meta.textContent = "";
    return;
  }
  // Log-scale both axes (price + listings span orders of magnitude).
  const w = 900, h = 340, padL = 64, padR = 18, padT = 18, padB = 36;
  const lx = enriched.map(r => Math.log10(listingValue(r)));
  const ly = enriched.map(r => Math.log10(rowPrice(r)));
  const minLx = Math.min(...lx), maxLx = Math.max(...lx);
  const minLy = Math.min(...ly), maxLy = Math.max(...ly);
  const X = v => padL + ((Math.log10(v) - minLx) / Math.max(maxLx - minLx, 0.001)) * (w - padL - padR);
  const Y = v => h - padB - ((Math.log10(v) - minLy) / Math.max(maxLy - minLy, 0.001)) * (h - padT - padB);
  // OLS regression on log-log -> price elasticity vs supply.
  const n = enriched.length;
  const sx = lx.reduce((a,b) => a+b, 0), sy = ly.reduce((a,b) => a+b, 0);
  const sxx = lx.reduce((a,b) => a+b*b, 0), sxy = lx.reduce((a,b,i) => a+b*ly[i], 0);
  const slope = (n*sxy - sx*sy) / Math.max(n*sxx - sx*sx, 0.0001);
  const intercept = (sy - slope*sx) / n;
  const meanX = sx/n, meanY = sy/n;
  const ssTot = ly.reduce((a,v) => a + (v-meanY)*(v-meanY), 0);
  const ssRes = ly.reduce((a,v,i) => { const yh = slope*lx[i]+intercept; return a + (v-yh)*(v-yh); }, 0);
  const r2 = 1 - ssRes / Math.max(ssTot, 0.0001);
  const corr = slope >= 0 ? "positive" : "negative";
  // Color by knife family
  const families = [...new Set(enriched.map(r => r.knife_type))];
  const palette = ["#f5b342","#ff7a1a","#56d89a","#79a9ff","#ff6b6b","#c084fc","#22d3ee","#f472b6","#a3e635","#fbbf24","#fb7185","#60a5fa","#34d399","#facc15","#a78bfa","#f87171","#2dd4bf","#fb923c","#94a3b8","#e879f9"];
  const colorOf = name => palette[families.indexOf(name) % palette.length];
  // Y gridlines at 10^k
  let grid = "";
  for (let pY = Math.ceil(minLy); pY <= Math.floor(maxLy); pY++) {
    const yy = Y(Math.pow(10, pY));
    grid += `<line class="ph-grid" x1="${padL}" y1="${yy}" x2="${w-padR}" y2="${yy}"></line>`;
    grid += `<text class="ph-axis" x="8" y="${yy+4}">${Math.pow(10,pY).toLocaleString()}</text>`;
  }
  for (let pX = Math.ceil(minLx); pX <= Math.floor(maxLx); pX++) {
    const xx = X(Math.pow(10, pX));
    grid += `<line class="ph-grid" x1="${xx}" y1="${padT}" x2="${xx}" y2="${h-padB}"></line>`;
    grid += `<text class="ph-axis" text-anchor="middle" x="${xx}" y="${h-12}">${Math.pow(10,pX).toLocaleString()}</text>`;
  }
  // Trend line
  const x1 = minLx, x2 = maxLx;
  const y1 = slope*x1 + intercept, y2 = slope*x2 + intercept;
  const trendLine = `<line x1="${X(Math.pow(10,x1))}" y1="${Y(Math.pow(10,y1))}" x2="${X(Math.pow(10,x2))}" y2="${Y(Math.pow(10,y2))}" stroke="rgba(245,179,66,.5)" stroke-width="2" stroke-dasharray="6 4"></line>`;
  // Dots
  const dots = enriched.map((r,i) => {
    const sel = selectedRow && r.goods_id === selectedRow.goods_id;
    return `<circle data-id="${escapeHtml(r.goods_id)}" cx="${X(listingValue(r)).toFixed(1)}" cy="${Y(rowPrice(r)).toFixed(1)}" r="${sel ? 6.5 : 4}" fill="${colorOf(r.knife_type)}" opacity="${sel ? 1 : 0.78}" stroke="${sel ? '#fff' : 'none'}" stroke-width="${sel ? 2 : 0}" style="cursor:pointer"></circle>`;
  }).join("");
  host.innerHTML = `
    <div style="position:relative;width:100%;height:100%">
      <svg class="ph-svg" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Supply vs price scatter">
        ${grid}
        ${trendLine}
        ${dots}
        <text class="ph-axis" text-anchor="middle" x="${w/2}" y="${h-2}">Listings (log)</text>
        <text class="ph-axis" transform="translate(14,${h/2}) rotate(-90)" text-anchor="middle">Price CNY (log)</text>
      </svg>
      <div class="ph-tip" id="supplyTip"></div>
    </div>`;
  // Legend in meta
  const legendHtml = families.map(f => `<span style="display:inline-flex;align-items:center;gap:4px;margin-right:10px"><span style="width:8px;height:8px;border-radius:999px;background:${colorOf(f)}"></span>${escapeHtml(f)}</span>`).join("");
  if (meta) meta.innerHTML = `<span><b style="color:${slope>=0?'var(--green)':'var(--red)'}">${corr} correlation</b> &middot; slope ${slope.toFixed(2)} &middot; R²=${r2.toFixed(2)}</span><span>${legendHtml}</span>`;
  // Hover tooltip
  const svg = host.querySelector("svg");
  const tip = host.querySelector("#supplyTip");
  svg.querySelectorAll("circle").forEach(c => {
    c.addEventListener("mouseenter", () => {
      const r = rows.find(x => x.goods_id === c.dataset.id);
      const rect = svg.getBoundingClientRect();
      const cx = +c.getAttribute("cx"), cy = +c.getAttribute("cy");
      tip.style.opacity = 1;
      tip.style.left = (cx / w * rect.width) + "px";
      tip.style.top = (cy / h * rect.height) + "px";
      tip.innerHTML = `<b>${escapeHtml(r.skin_name||r.item_name)}</b><br>${money(rowPrice(r))} &middot; Sell ${listingValue(r).toLocaleString()}`;
    });
    c.addEventListener("mouseleave", () => { tip.style.opacity = 0; });
    c.addEventListener("click", () => {
      const r = rows.find(x => x.goods_id === c.dataset.id);
      if (r) selectRow(r);
    });
  });
}
function render() { renderKnifeRail(); renderFamilyCards(); renderFamilyBrowser(); renderDetail(); renderTable(); renderPriceChart(); renderSupplyChart(); renderRelatedItems(); renderInsights(); renderSourceHealth(); renderMarketSignals(); }
skinSearch?.addEventListener("input", renderFamilyBrowser);
search.addEventListener("input", () => { tableLimit = 300; render(); });
knifeType.addEventListener("change", () => { tableLimit = 300; render(); });
condition.addEventListener("change", () => { tableLimit = 300; render(); });
sort.addEventListener("change", () => { tableLimit = 300; render(); });
document.getElementById("resetFilters")?.addEventListener("click", () => {
  search.value = "";
  knifeType.value = "";
  condition.value = "";
  sort.value = "price-desc";
  selectedFamily = "";
  if (skinSearch) skinSearch.value = "";
  tableLimit = 300;
  render();
});
loadMore.addEventListener("click", () => { tableLimit += 300; render(); });
rangeToggle?.querySelectorAll("button").forEach(btn => {
  btn.addEventListener("click", () => {
    rangeDays = Number(btn.dataset.days) || 90;
    rangeToggle.querySelectorAll("button").forEach(b => b.classList.toggle("active", b === btn));
    renderPriceChart();
  });
});
render();
</script>
</body>
</html>"""
    icons = {
        "icon_layers": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3 3 8l9 5 9-5-9-5Z" stroke="currentColor" stroke-width="2"/><path d="m3 13 9 5 9-5" stroke="currentColor" stroke-width="2"/><path d="m3 18 9 5 9-5" stroke="currentColor" stroke-width="2"/></svg>',
        "icon_knife": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M14 3l7 7-3 3-7-7 3-3Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M11 6 3 14v4h4l8-8" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
        "icon_chart": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 19V5M4 19h16M8 16l3-5 4 3 5-8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "icon_flash": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m13 2-8 12h7l-1 8 8-12h-7l1-8Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
        "icon_target": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/></svg>',
    }
    # Pre-render the initial selected-item details so "Loading item" never
    # appears to the user, even if JS is slow or blocked.
    initial_row = max(
        rows,
        key=lambda r: (r.get("price_cny") or 0),
        default=None,
    )
    if initial_row:
        initial_detail = {
            "name": str(initial_row.get("skin_name") or initial_row.get("item_name") or "Select an item"),
            "image": str(initial_row.get("image_url") or _static_item_image_url("Knife")),
            "quality": str(initial_row.get("wear") or initial_row.get("condition") or "N/A"),
            "category": str(initial_row.get("condition") or "N/A"),
            "type": str(initial_row.get("knife_type") or "N/A"),
            "price": _money(initial_row.get("price_cny")),
            "ref": _money(initial_row.get("reference_price_cny")),
            "spread": _spread(initial_row),
            "search": "https://buff.163.com/market/csgo#tab=selling&page_num=1&search="
            + urllib.parse.quote(str(initial_row.get("market_hash_name") or "")),
        }
    else:
        initial_detail = {
            "name": "Select an item",
            "image": _static_item_image_url("Knife"),
            "quality": "N/A",
            "category": "N/A",
            "type": "N/A",
            "price": "N/A",
            "ref": "N/A",
            "spread": "N/A",
            "search": "https://buff.163.com/market/csgo",
        }

    replacements = {
        "__UPDATED_AT__": html.escape(updated_at),
        "__COUNT__": f"{count:,}",
        "__AVG_PRICE__": f"{avg_price:,.2f}",
        "__HIGH_PRICE__": f"{high_price:,.2f}",
        "__LOW_PRICE__": f"{low_price:,.2f}",
        "__PREMIUM_ROWS__": f"{premium_rows:,}",
        "__TOP_FAMILY__": html.escape(top_family),
        "__TOP_KNIFE_TYPE__": html.escape(top_knife_type),
        "__KNIFE_FAMILY_COUNT__": f"{len(knife_types):,}",
        "__ROWS_JSON__": payload,
        "__KNIFE_TYPES_JSON__": knife_types_payload,
        "__INITIAL_TABLE_ROWS__": initial_rows_html,
        "__ICON_LAYERS__": icons["icon_layers"],
        "__ICON_KNIFE__": icons["icon_knife"],
        "__ICON_CHART__": icons["icon_chart"],
        "__ICON_FLASH__": icons["icon_flash"],
        "__ICON_TARGET__": icons["icon_target"],
        "__INITIAL_DETAIL_NAME__": html.escape(initial_detail["name"]),
        "__INITIAL_DETAIL_IMAGE__": html.escape(initial_detail["image"]),
        "__INITIAL_DETAIL_QUALITY__": html.escape(initial_detail["quality"]),
        "__INITIAL_DETAIL_CATEGORY__": html.escape(initial_detail["category"]),
        "__INITIAL_DETAIL_TYPE__": html.escape(initial_detail["type"]),
        "__INITIAL_DETAIL_PRICE__": html.escape(initial_detail["price"]),
        "__INITIAL_DETAIL_REF__": html.escape(initial_detail["ref"]),
        "__INITIAL_DETAIL_SPREAD__": html.escape(initial_detail["spread"]),
        "__INITIAL_BUFF_SEARCH__": html.escape(initial_detail["search"]),
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def _alert_cookie_expired(ssm_client: Any, fetch_errors: list[str]) -> None:
    """One-shot Discord ping when the BUFF cookie has stopped working."""
    import os  # noqa: PLC0415

    webhook_param = os.getenv("DISCORD_WEBHOOK_SSM_PARAM", "").strip()
    if not webhook_param:
        print(f"buff_cookie_expired errors={fetch_errors}", flush=True)
        return
    try:
        out = ssm_client.get_parameter(Name=webhook_param, WithDecryption=True)
        webhook = str((out.get("Parameter") or {}).get("Value") or "")
    except Exception:  # noqa: BLE001 - best effort
        return
    if not webhook:
        return
    from src.aws_lambda.alerts import send_discord_alert  # noqa: PLC0415

    send_discord_alert(
        webhook,
        "cookie_expired",
        {
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "items_scraped": 0,
            "items_saved": 0,
            "errors": ["BUFF cookie in SSM rejected — Sell(N) and price history are stale until rotated."] + fetch_errors[:2],
        },
    )


def _enrich_listings(
    ssm_client: Any,
    rows: list[dict[str, Any]],
    errors: list[str],
    s3_client: Any = None,
    bucket: str = "",
    key_prefix: str = "",
) -> None:
    """Add real BUFF listing counts + price history when a cookie is configured.

    Reads a BUFF session cookie from SSM (BUFF_COOKIE_SSM_PARAM, default
    ``/buff163/cookie``). No cookie -> silently skipped (dashboard stays
    price-only). Enriches rows with Sell(N) listing counts and real buff_url,
    then fetches BUFF price history for the top items and writes it to
    ``current/price_history.json`` for the time-series chart.
    """
    import os  # noqa: PLC0415

    param = os.getenv("BUFF_COOKIE_SSM_PARAM", "/buff163/cookie").strip()
    if not param:
        return
    try:
        out = ssm_client.get_parameter(Name=param, WithDecryption=True)
        cookie = str((out.get("Parameter") or {}).get("Value") or "")
    except Exception:  # noqa: BLE001 - no cookie configured -> price-only
        return
    if not cookie:
        return

    try:
        from src.aws_lambda.buff_listings import (  # noqa: PLC0415
            build_price_history,
            enrich_rows,
            fetch_listing_map,
        )

        pages = int(os.getenv("LISTING_PAGES", "4"))
        listing_map, fetch_errors = fetch_listing_map(cookie, pages=pages)
        errors.extend(fetch_errors)
        cookie_expired = any(
            "Login Required" in e or "Forbidden" in e or "401" in e
            for e in fetch_errors
        )
        if not listing_map:
            if cookie_expired or fetch_errors:
                _alert_cookie_expired(ssm_client, fetch_errors)
            return
        count = enrich_rows(rows, listing_map)
        print(f"listings_enriched={count} listing_map_size={len(listing_map)}", flush=True)

        # Price history for the top enriched items (those with a buff goods_id).
        if s3_client and bucket:
            history_n = int(os.getenv("LISTING_HISTORY_N", "50"))
            history_days = int(os.getenv("HISTORY_DAYS", "180"))
            enriched = [r for r in rows if r.get("buff_url") and r.get("listing_count") is not None]
            enriched.sort(key=lambda r: (r.get("price_cny") or 0), reverse=True)
            goods_ids: list[int] = []
            for r in enriched[:history_n]:
                try:
                    goods_ids.append(int(str(r["buff_url"]).rsplit("/", 1)[-1]))
                except (ValueError, KeyError):
                    continue
            if goods_ids:
                history = build_price_history(cookie, goods_ids, days=history_days)
                if history:
                    from src.aws_lambda.s3_store import put_json  # noqa: PLC0415

                    put_json(s3_client, bucket, f"{key_prefix}current/price_history.json", history)
                    print(f"price_history_items={len(history)}", flush=True)
    except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
        errors.append(f"listing_enrich_failed: {type(exc).__name__}")


def lambda_handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, Any]:
    """Free-tier Lambda entry.

    Reuses the existing in-file scrape (_snapshots, _render_html) and wires in:
      - S3 hash-dedupe (src.aws_lambda.s3_store) -> stays under Free Tier PUTs
      - Append-only history + raw backup with lifecycle expiry
      - Optional Google Sheets write (WRITE_SHEETS=1)
      - Optional Discord failure alert (webhook from SSM)
    Never raises: errors are captured into the JSON summary.
    """
    started = time.monotonic()
    event = event or {}
    bucket = os.environ.get("STATIC_SITE_BUCKET") or os.environ.get("S3_BUCKET", "")
    prefix = os.getenv("STATIC_SITE_PREFIX", "").strip("/")
    key_prefix = f"{prefix}/" if prefix else ""
    updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    iso_now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if event.get("mode") == "health_check" or os.getenv("BUFF_HEALTH_CHECK") == "1":
        return {
            "status": "success",
            "items_scraped": 0,
            "items_saved": 0,
            "errors": [],
            "timestamp": iso_now,
            "mode": "health_check",
            "bucket": bucket,
        }

    if not bucket:
        return {
            "status": "error",
            "items_scraped": 0,
            "items_saved": 0,
            "errors": ["bucket env not set (STATIC_SITE_BUCKET or S3_BUCKET)"],
            "timestamp": iso_now,
        }

    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    items_saved = 0
    html_body = ""

    import boto3  # noqa: PLC0415

    s3 = boto3.client("s3")
    ssm = boto3.client("ssm")

    # Lazy imports keep cold-start cheap when nothing changed.
    from src.aws_lambda.s3_store import put_json, put_text  # noqa: PLC0415

    try:
        rows = _snapshots()
        # Optional: enrich the most-listed knives with real BUFF listing counts
        # (Sell(N)) when a BUFF cookie is configured in SSM. No-op otherwise.
        _enrich_listings(ssm, rows, errors, s3_client=s3, bucket=bucket, key_prefix=key_prefix)
        html_body = _render_html(updated_at, rows)
        _validate_static_payload(rows, html_body)
    except Exception as exc:  # noqa: BLE001 - boundary
        errors.append(f"scrape_failed: {type(exc).__name__}")

    if rows:
        try:
            # Static dashboard payloads (overwrite latest, dedupe by sha).
            data_result = put_json(
                s3,
                bucket,
                f"{key_prefix}data.json",
                {"updated_at": updated_at, "rows": rows},
            )
            put_text(
                s3,
                bucket,
                f"{key_prefix}index.html",
                html_body,
                content_type="text/html; charset=utf-8",
            )
            put_json(
                s3,
                bucket,
                f"{key_prefix}current/snapshots.json",
                rows,
            )
            put_json(
                s3,
                bucket,
                f"{key_prefix}current/meta.json",
                {"last_run_at": iso_now, "items": len(rows), "version": 1},
                dedupe=False,
            )
            # Coverage report, global summary, per-family aggregation.
            put_json(s3, bucket, f"{key_prefix}data/data-quality.json", _data_quality(rows, iso_now))
            put_json(s3, bucket, f"{key_prefix}data/market-summary.json", _market_summary(rows, iso_now))
            put_json(s3, bucket, f"{key_prefix}data/market-items.json", rows)
            put_json(s3, bucket, f"{key_prefix}data/families.json", _families_summary(rows))
            # Append-only history backup only when content actually changed.
            if data_result.get("written"):
                now_dt = datetime.now(UTC)
                yyyy = f"{now_dt.year:04d}"
                mm = f"{now_dt.month:02d}"
                dd = f"{now_dt.day:02d}"
                hhmmss = now_dt.strftime("%H%M%S")
                put_json(
                    s3,
                    bucket,
                    f"{key_prefix}history/{yyyy}/{mm}/{dd}/snapshots-{hhmmss}.json",
                    rows,
                    dedupe=False,
                )
            items_saved = len(rows)
        except Exception as exc:  # noqa: BLE001 - boundary
            errors.append(f"s3_write_failed: {type(exc).__name__}")

    # Optional Google Sheets write — gated by WRITE_SHEETS=1.
    sheets_saved = 0
    if os.getenv("WRITE_SHEETS", "").strip() in {"1", "true", "True"}:
        try:
            from src.aws_lambda.handler_sheets import write_sheets  # noqa: PLC0415

            sheets_saved, sheets_errors = write_sheets(ssm, rows, iso_now)
            errors.extend(sheets_errors)
        except Exception as exc:  # noqa: BLE001 - boundary
            errors.append(f"sheets_write_failed: {type(exc).__name__}")

    status = "success" if rows and not errors else ("partial_success" if rows else "error")
    summary: dict[str, Any] = {
        "status": status,
        "ok": status == "success",
        "rows": len(rows),  # legacy compatibility
        "items_scraped": len(rows),
        "items_saved": items_saved,
        "items_saved_sheets": sheets_saved,
        "errors": errors,
        "timestamp": iso_now,
        "bucket": bucket,
        "prefix": prefix,
        "duration_seconds": round(time.monotonic() - started, 2),
    }

    # Failure alert (one Discord POST max, redacted webhook from SSM).
    if status != "success":
        try:
            from src.aws_lambda.alerts import send_discord_alert  # noqa: PLC0415

            webhook_param = os.getenv("DISCORD_WEBHOOK_SSM_PARAM", "").strip()
            if webhook_param:
                ssm_out = ssm.get_parameter(Name=webhook_param, WithDecryption=True)
                webhook = (ssm_out.get("Parameter") or {}).get("Value") or ""
                if webhook:
                    send_discord_alert(webhook, status, summary)
        except Exception:  # noqa: BLE001 - alert is best-effort
            pass

    return summary
