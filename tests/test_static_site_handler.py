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
    assert b"All knife list" in html_body
    assert b"knifeRail" in html_body
    assert b"familyCards" in html_body
    assert b"Load more" in html_body
    assert b"skin-thumb" in html_body
    assert b"Buff.163 item detail" in html_body
    assert b"detailImage" in html_body
    assert b"wearButtons" in html_body
    assert b"Related items" in html_body
    assert b"relatedItems" in html_body
    assert b"Selected item price history" in html_body
    assert b"renderTimeSeries" in html_body
    assert b"current/listing_history.json" in html_body
    assert b"Sell count" in html_body
    assert b"listingHistory" in html_body
    assert b"On sale" in html_body  # family cards supply stat
    assert b"Most on sale (supply pressure)" in html_body
    assert b"Scarcest supply" in html_body
    assert b"family view" in html_body  # scatter scoped to selected family
    assert b"selectedFamilyRows" in html_body
    assert b"selected-row" in html_body
    assert b"FALLBACK_IMG" in html_body
    # Listing UI removed: csgotrader feed has no order-book depth.
    assert b"Selected item listing view" not in html_body
    assert b"Liquidity signals" not in html_body
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
    static_site_handler._validate_static_payload(rows, html_body)


class _HistoryS3:
    """get_object/put_object pair backed by an in-memory dict of bodies."""

    def __init__(self):
        self.bodies: dict[str, bytes] = {}
        self.put_count = 0

    def get_object(self, Bucket, Key):
        if Key not in self.bodies:
            raise Exception("NoSuchKey")
        import io

        return {"Body": io.BytesIO(self.bodies[Key])}

    def put_object(self, **kwargs):
        self.bodies[kwargs["Key"]] = kwargs["Body"]
        self.put_count += 1
        return {}


def _history_rows():
    return [
        {"buff_url": "https://buff.163.com/goods/42587", "listing_count": 251},
        {"buff_url": "https://buff.163.com/goods/776", "listing_count": 88},
        {"buff_url": None, "listing_count": 10},  # no goods_id -> skipped
        {"buff_url": "https://buff.163.com/goods/999", "listing_count": None},  # unknown -> skipped
    ]


def test_append_listing_history_first_run_writes_one_point_per_item():
    import json

    s3 = _HistoryS3()
    static_site_handler._append_listing_history(s3, "bucket", "", _history_rows())

    assert s3.put_count == 1
    data = json.loads(s3.bodies["current/listing_history.json"])
    assert set(data) == {"42587", "776"}
    assert len(data["42587"]) == 1
    assert data["42587"][0][1] == 251
    assert data["776"][0][1] == 88


def test_append_listing_history_same_day_rerun_refreshes_not_duplicates():
    import json

    s3 = _HistoryS3()
    static_site_handler._append_listing_history(s3, "bucket", "", _history_rows())
    rows = _history_rows()
    rows[0]["listing_count"] = 240  # count moved later same day
    static_site_handler._append_listing_history(s3, "bucket", "", rows)

    data = json.loads(s3.bodies["current/listing_history.json"])
    assert len(data["42587"]) == 1  # same UTC day -> point replaced, not appended
    assert data["42587"][0][1] == 240


def test_append_listing_history_appends_new_day_and_caps_length():
    import json

    s3 = _HistoryS3()
    # Pre-seed: 400 old points ending well in the past for one item.
    old_ms = 1700000000000
    seeded = {"42587": [[old_ms + i * 86400000, 100 + i] for i in range(400)]}
    s3.bodies["current/listing_history.json"] = json.dumps(seeded).encode("utf-8")

    static_site_handler._append_listing_history(
        s3, "bucket", "", [{"buff_url": "https://buff.163.com/goods/42587", "listing_count": 251}]
    )

    data = json.loads(s3.bodies["current/listing_history.json"])
    points = data["42587"]
    assert len(points) == 400  # capped: oldest dropped
    assert points[-1][1] == 251  # today appended last


def test_append_listing_history_no_enriched_rows_writes_nothing():
    s3 = _HistoryS3()
    static_site_handler._append_listing_history(
        s3, "bucket", "", [{"buff_url": None, "listing_count": None}]
    )
    assert s3.put_count == 0


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
