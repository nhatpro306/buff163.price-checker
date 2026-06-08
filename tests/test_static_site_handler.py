from __future__ import annotations

import sys
from types import SimpleNamespace

import static_site_handler


def test_static_site_handler_writes_html_and_json(monkeypatch):
    monkeypatch.setenv("STATIC_SITE_BUCKET", "site-bucket")
    monkeypatch.setenv("BUFF_TRACK_KEYWORDS", "Karambit")
    monkeypatch.setattr(
        static_site_handler,
        "_fetch_json",
        lambda _url: {
            "Karambit | Doppler (Factory New)": {
                "starting_at": {"price": "100"},
                "highest_order": {"price": "95"},
            },
            "AK-47 | Redline (Field-Tested)": {
                "starting_at": {"price": "10"},
                "highest_order": {"price": "9"},
            },
        },
    )
    writes = []

    class FakeS3:
        def put_object(self, **kwargs):
            writes.append(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "boto3",
        SimpleNamespace(client=lambda service_name: FakeS3()),
    )

    result = static_site_handler.lambda_handler({}, None)

    assert result["ok"] is True
    assert result["rows"] == 1
    written_keys = {write["Key"] for write in writes}
    # Free-tier write set: legacy static-dashboard pair + canonical current/* keys
    # + a history snapshot when content changed. Extra keys are allowed; the
    # core pair must always be present.
    assert {"index.html", "data.json"}.issubset(written_keys)
    assert "current/snapshots.json" in written_keys
    assert "current/meta.json" in written_keys
    assert any(k.startswith("history/") for k in written_keys)
    html_body = next(write["Body"] for write in writes if write["Key"] == "index.html")
    assert b"Karambit | Doppler" in html_body
    assert b'<tbody id="rows"><tr' in html_body
    assert b"BUFF163 Market Intelligence" in html_body
    assert b"underpriced CS2 knives faster" in html_body
    assert b"priceChart" in html_body
    assert b"Listing count" in html_body
    assert b"All knife list" in html_body
    assert b"knifeRail" in html_body
    assert b"Load more" in html_body
    assert b"Knife pictures" in html_body
    assert b"knifeAtlas" in html_body
    assert b"skin-thumb" in html_body
    assert b"Buff.163 item detail" in html_body
    assert b"detailImage" in html_body
    assert b"wearButtons" in html_body
    assert b"Related items" in html_body
    assert b"relatedItems" in html_body
    assert b"Selected item price view" in html_body
    assert b"selectedFamilyRows" in html_body
    assert b"selected-row" in html_body
    assert b"Listing data unavailable" in html_body
    data_body = next(write["Body"] for write in writes if write["Key"] == "data.json")
    assert b"knife_type" in data_body
    assert b"item_name" in data_body
    assert b'"wear":"FN"' in data_body  # compact json (no spaces) saves S3 bytes
    assert b"listing_count" in data_body
    assert b"image_url" in data_body
    assert b"category" in data_body


def test_static_site_handler_filters_bad_prices_and_validates_fallbacks(monkeypatch):
    monkeypatch.setenv("BUFF_TRACK_KEYWORDS", "Karambit")
    monkeypatch.setattr(
        static_site_handler,
        "_fetch_json",
        lambda _url: {
            "Karambit | Doppler (Factory New)": {
                "starting_at": {"price": "0.01"},
                "highest_order": {"price": "0.01"},
            },
            "Karambit | Fade (Minimal Wear)": {
                "starting_at": {"price": "100"},
                "highest_order": {"price": "95"},
            },
        },
    )

    rows = static_site_handler._snapshots()
    html_body = static_site_handler._render_html("2026-06-06 00:00:00", rows)

    assert len(rows) == 1
    assert rows[0]["price"] >= 1
    assert rows[0]["image_url"]
    assert rows[0]["category"]
    assert rows[0]["wear"] == "MW"
    assert '<tbody id="rows"><tr' in html_body
    assert "selectedFamilyRows" in html_body
    assert "Listing data unavailable" in html_body
    static_site_handler._validate_static_payload(rows, html_body)


def test_static_site_handler_keeps_m9_bayonet_separate(monkeypatch):
    monkeypatch.setenv("BUFF_TRACK_KEYWORDS", "Bayonet,M9 Bayonet")
    monkeypatch.setattr(
        static_site_handler,
        "_fetch_json",
        lambda _url: {
            "M9 Bayonet | Doppler (Factory New)": {
                "starting_at": {"price": "100"},
                "highest_order": {"price": "95"},
            },
            "Bayonet | Marble Fade (Factory New)": {
                "starting_at": {"price": "80"},
                "highest_order": {"price": "70"},
            },
        },
    )

    rows = static_site_handler._snapshots()

    assert {row["knife_type"] for row in rows} == {"M9 Bayonet", "Bayonet"}
