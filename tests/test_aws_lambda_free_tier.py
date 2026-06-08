from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.aws_lambda.alerts import send_discord_alert
from src.aws_lambda.config import load_config
from src.aws_lambda.s3_store import put_json, put_text

# --- config -----------------------------------------------------------------

def test_load_config_defaults(monkeypatch):
    for k in (
        "S3_BUCKET",
        "AWS_REGION",
        "LOG_LEVEL",
        "REQUEST_TIMEOUT_SECONDS",
        "MAX_RETRIES",
        "PRICE_DROP_ALERT_PERCENT",
        "WRITE_SHEETS",
        "SPREADSHEET_ID",
        "WORKSHEET_NAME",
        "SCRAPER_TARGETS",
        "HISTORY_KEEP_DAYS",
        "RAW_KEEP_DAYS",
    ):
        monkeypatch.delenv(k, raising=False)

    cfg = load_config()
    assert cfg.s3_bucket == ""
    assert cfg.region == "ap-northeast-1"
    assert cfg.log_level == "INFO"
    assert cfg.request_timeout_s == 15
    assert cfg.max_retries == 3
    assert cfg.write_sheets is False
    assert cfg.scraper_targets == []
    assert cfg.history_keep_days == 90
    assert cfg.raw_keep_days == 14


def test_load_config_overrides(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "my-bucket")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-1")
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("MAX_RETRIES", "5")
    monkeypatch.setenv("WRITE_SHEETS", "1")
    monkeypatch.setenv("SCRAPER_TARGETS", "1, 2 ,3,,")
    monkeypatch.setenv("PRICE_DROP_ALERT_PERCENT", "12.5")

    cfg = load_config()
    assert cfg.s3_bucket == "my-bucket"
    assert cfg.region == "ap-southeast-1"
    assert cfg.request_timeout_s == 30
    assert cfg.max_retries == 5
    assert cfg.write_sheets is True
    assert cfg.scraper_targets == ["1", "2", "3"]
    assert cfg.price_drop_alert_percent == pytest.approx(12.5)


# --- s3 dedupe --------------------------------------------------------------

class _FakeS3:
    def __init__(self, existing: dict[str, str] | None = None):
        self.objects: dict[str, dict[str, Any]] = {}
        if existing:
            for key, sha in existing.items():
                self.objects[key] = {"Metadata": {"sha": sha}}
        self.put_calls: list[dict[str, Any]] = []

    def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise Exception("NoSuchKey")
        return self.objects[Key]

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.put_calls.append(kwargs)
        self.objects[kwargs["Key"]] = {"Metadata": kwargs.get("Metadata", {})}
        return {}


def test_put_json_writes_when_no_existing():
    s3 = _FakeS3()
    result = put_json(s3, "b", "k.json", {"a": 1})
    assert result["written"] is True
    assert len(s3.put_calls) == 1
    assert s3.put_calls[0]["ContentType"].startswith("application/json")


def test_put_json_skips_when_sha_matches():
    payload = {"a": 1}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    import hashlib

    sha = hashlib.sha256(body).hexdigest()
    s3 = _FakeS3(existing={"k.json": sha})
    result = put_json(s3, "b", "k.json", payload)
    assert result["written"] is False
    assert s3.put_calls == []


def test_put_json_writes_when_payload_changed():
    s3 = _FakeS3(existing={"k.json": "deadbeef"})
    result = put_json(s3, "b", "k.json", {"a": 2})
    assert result["written"] is True
    assert len(s3.put_calls) == 1


def test_put_json_no_dedupe_always_writes():
    payload = {"a": 1}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    import hashlib

    sha = hashlib.sha256(body).hexdigest()
    s3 = _FakeS3(existing={"k.json": sha})
    result = put_json(s3, "b", "k.json", payload, dedupe=False)
    assert result["written"] is True


def test_put_text_html():
    s3 = _FakeS3()
    result = put_text(s3, "b", "index.html", "<html></html>", content_type="text/html")
    assert result["written"] is True
    assert s3.put_calls[0]["ContentType"] == "text/html"


# --- alerts -----------------------------------------------------------------

def test_send_discord_alert_no_url_is_noop():
    assert send_discord_alert("", "error", {}) is False


def test_send_discord_alert_failure_is_safe():
    summary = {"timestamp": "now", "items_scraped": 0, "items_saved": 0, "errors": ["x"]}
    with patch("urllib.request.urlopen", side_effect=Exception("net down")):
        assert send_discord_alert("https://example.invalid/hook", "error", summary) is False


def test_send_discord_alert_success_returns_true():
    summary = {"timestamp": "now", "items_scraped": 1, "items_saved": 1, "errors": []}
    resp = MagicMock()
    resp.read.return_value = b""
    resp.__enter__ = lambda s: resp
    resp.__exit__ = lambda *a: None
    with patch("urllib.request.urlopen", return_value=resp):
        assert send_discord_alert("https://example.invalid/hook", "partial_success", summary) is True


# --- buff listing enrichment ------------------------------------------------

def test_buff_fetch_listing_map_no_cookie_is_noop():
    from src.aws_lambda.buff_listings import fetch_listing_map

    out, errors = fetch_listing_map("")
    assert out == {}
    assert "buff_cookie_absent" in errors


def test_buff_enrich_rows_matches_by_normalized_name():
    from src.aws_lambda.buff_listings import enrich_rows

    rows = [
        {"market_hash_name": "★ Butterfly Knife | Tiger Tooth (Factory New)", "listing_count": None},
        {"market_hash_name": "M9 Bayonet | Doppler (Factory New)", "listing_count": None},
    ]
    listing_map = {
        "butterfly knife | tiger tooth (factory new)": {"goods_id": 42587, "listing_count": 251, "sell_min_price": "7640"},
    }
    enriched = enrich_rows(rows, listing_map)
    assert enriched == 1
    assert rows[0]["listing_count"] == 251
    assert rows[0]["buff_url"] == "https://buff.163.com/goods/42587"
    assert rows[1]["listing_count"] is None  # no match -> stays unknown


def test_buff_fetch_listing_map_parses_payload():
    from src.aws_lambda import buff_listings

    payload = {
        "code": "OK",
        "data": {"items": [
            {"id": 42587, "market_hash_name": "★ Butterfly Knife | Tiger Tooth (Factory New)", "sell_num": 251, "sell_min_price": "7640"},
            {"id": 776, "market_hash_name": "★ Karambit | Doppler (Factory New)", "sell_num": 88},
        ]},
    }
    with patch.object(buff_listings, "_get_json", return_value=payload), \
         patch.object(buff_listings.time, "sleep", lambda *_a: None):
        out, errors = buff_listings.fetch_listing_map("session=x", pages=1)
    assert errors == []
    assert out["butterfly knife | tiger tooth (factory new)"]["goods_id"] == 42587
    assert out["butterfly knife | tiger tooth (factory new)"]["listing_count"] == 251
    assert out["karambit | doppler (factory new)"]["listing_count"] == 88
