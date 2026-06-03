from __future__ import annotations

import sqlite3

from market_models import MarketSnapshot
from src import orchestrator


def _snapshot(goods_id: str, listings: int) -> MarketSnapshot:
    return MarketSnapshot(
        goods_id=goods_id,
        family="Bayonet",
        skin_name="Bayonet",
        condition="Unknown",
        price=1600,
        listings=listings,
        buy_orders=2 if listings else 0,
        reference_price=None,
        image_url="",
        observed_orders=0,
    )


def test_local_sqlite_writes_final_merged_snapshots(monkeypatch, tmp_path):
    db_path = tmp_path / "buff.sqlite3"
    direct = _snapshot("755862", 9)
    fallback = _snapshot("csgotrader:bayonet", 0)

    class Client:
        def discover_high_value_catalog(self, **kwargs):
            kwargs["on_snapshot"](direct)
            return [direct]

    monkeypatch.setenv("BUFF_WRITE_SQLITE", "1")
    monkeypatch.setenv("BUFF_WRITE_SHEETS", "0")
    monkeypatch.setenv("BUFF_FALLBACK_CSGOTRADER", "1")
    monkeypatch.setenv("BUFF_FULL_CATALOG", "0")
    monkeypatch.setenv("BUFF_SQLITE_PATH", str(db_path))
    monkeypatch.setattr(orchestrator, "BuffPriceClient", Client)
    monkeypatch.setattr(orchestrator, "get_track_keywords", lambda: ["Bayonet"])
    monkeypatch.setattr(orchestrator, "get_search_keywords", lambda keywords: keywords)
    monkeypatch.setattr(orchestrator, "get_seed_goods_ids", lambda: [])
    monkeypatch.setattr(orchestrator, "csgotrader_snapshots", lambda *_args: [fallback])

    orchestrator.run()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("""
            SELECT g.goods_id, s.listings
            FROM snapshots s
            JOIN goods g ON g.goods_id = s.goods_id
            ORDER BY g.goods_id
            """).fetchall()
    finally:
        conn.close()

    assert rows == [("755862", 9)]
