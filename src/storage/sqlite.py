from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from market_config import HISTORY_HEADERS
from market_models import MarketSnapshot


def sqlite_connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def sqlite_init(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS goods (
            goods_id TEXT PRIMARY KEY,
            family TEXT NOT NULL,
            knife_type TEXT NOT NULL,
            skin_name TEXT NOT NULL,
            condition TEXT NOT NULL,
            reference_price REAL,
            image_url TEXT
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            goods_id TEXT NOT NULL REFERENCES goods(goods_id) ON DELETE CASCADE,
            price REAL NOT NULL,
            listings INTEGER NOT NULL,
            buy_orders INTEGER NOT NULL,
            observed_orders INTEGER NOT NULL,
            UNIQUE(ts, goods_id)
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_goods_ts ON snapshots(goods_id, ts);
        CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
        """)
    goods_cols = {row[1] for row in conn.execute("PRAGMA table_info(goods);")}
    if "reference_price" not in goods_cols:
        conn.execute("ALTER TABLE goods ADD COLUMN reference_price REAL;")
    if "image_url" not in goods_cols:
        conn.execute("ALTER TABLE goods ADD COLUMN image_url TEXT;")

    snapshots_cols = {row[1] for row in conn.execute("PRAGMA table_info(snapshots);")}
    if "buy_orders" not in snapshots_cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN buy_orders INTEGER NOT NULL DEFAULT 0;")
    if "observed_orders" not in snapshots_cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN observed_orders INTEGER NOT NULL DEFAULT 0;")


def sqlite_upsert_snapshot(
    conn: sqlite3.Connection,
    *,
    timestamp: str,
    snapshot: MarketSnapshot,
) -> None:
    conn.execute(
        """
        INSERT INTO goods(goods_id, family, knife_type, skin_name, condition, reference_price, image_url)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(goods_id) DO UPDATE SET
            family=excluded.family,
            knife_type=excluded.knife_type,
            skin_name=excluded.skin_name,
            condition=excluded.condition,
            reference_price=excluded.reference_price,
            image_url=excluded.image_url;
        """,
        (
            snapshot.goods_id,
            snapshot.family,
            snapshot.knife_type,
            snapshot.skin_name,
            snapshot.condition,
            snapshot.reference_price,
            snapshot.image_url,
        ),
    )
    conn.execute(
        """
        INSERT INTO snapshots(ts, goods_id, price, listings, buy_orders, observed_orders)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(ts, goods_id) DO UPDATE SET
            price=excluded.price,
            listings=excluded.listings,
            buy_orders=excluded.buy_orders,
            observed_orders=excluded.observed_orders;
        """,
        (
            timestamp,
            snapshot.goods_id,
            snapshot.price,
            snapshot.listings,
            snapshot.buy_orders,
            snapshot.observed_orders,
        ),
    )


def sqlite_write_snapshots(db_path: str, snapshots: list[MarketSnapshot], timestamp: str) -> None:
    if not snapshots:
        return
    conn = sqlite_connect(db_path)
    try:
        sqlite_init(conn)
        with conn:
            for snapshot in snapshots:
                sqlite_upsert_snapshot(conn, timestamp=timestamp, snapshot=snapshot)
    finally:
        conn.close()


def sqlite_load_history_frame(db_path: str) -> pd.DataFrame:
    if not Path(db_path).exists():
        return pd.DataFrame(columns=HISTORY_HEADERS)
    conn = sqlite_connect(db_path)
    try:
        sqlite_init(conn)
        query = """
        SELECT
            s.ts AS "Timestamp",
            g.goods_id AS "Goods ID",
            g.family AS "Family",
            g.knife_type AS "Knife Type",
            g.skin_name AS "Skin Name",
            g.condition AS "Condition",
            s.price AS "Price",
            s.listings AS "Listings",
            s.buy_orders AS "Buy Orders",
            g.reference_price AS "Reference Price",
            g.image_url AS "Image URL",
            s.observed_orders AS "Observed Orders"
        FROM snapshots s
        JOIN goods g ON g.goods_id = s.goods_id
        ORDER BY s.ts ASC;
        """
        frame = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    return frame.reindex(columns=HISTORY_HEADERS)
