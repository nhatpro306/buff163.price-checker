from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.storage import PageMetaCache


def test_set_get_round_trip(tmp_path):
    cache = PageMetaCache(str(tmp_path / "cache.sqlite3"))
    cache.set("1", {"a": 1})
    assert cache.get("1") == {"a": 1}


def test_get_returns_none_for_expired(tmp_path):
    db = tmp_path / "cache.sqlite3"
    cache = PageMetaCache(str(db))
    cache.set("1", {"a": 1})
    with cache._conn() as conn:
        old = (datetime.now(UTC) - timedelta(hours=100)).isoformat()
        conn.execute("UPDATE page_meta SET fetched_at = ? WHERE goods_id = ?", (old, "1"))
    assert cache.get("1", max_age_hours=1) is None


def test_get_returns_data_for_fresh(tmp_path):
    cache = PageMetaCache(str(tmp_path / "cache.sqlite3"))
    cache.set("x", {"x": "y"})
    assert cache.get("x", max_age_hours=48) == {"x": "y"}
