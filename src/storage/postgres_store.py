from __future__ import annotations

import os
from uuid import uuid4

import pandas as pd

from market_config import HISTORY_HEADERS
from market_models import MarketSnapshot
from src.db.postgres_client import transaction
from src.redaction import redact_secrets
from src.results import ScrapeRunSummary
from src.storage.base import StorageBackendBase


class PostgresStore(StorageBackendBase):
    def __init__(self) -> None:
        from src.db.postgres_client import _database_url

        _database_url()
        if os.getenv("BUFF_AUTO_MIGRATE_POSTGRES", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            from src.db.postgres_client import apply_pending_migrations

            applied = apply_pending_migrations()
            if applied:
                print(f"Applied PostgreSQL migrations: {', '.join(applied)}")

    def check_connection(self) -> None:
        with transaction() as cur:
            cur.execute("SELECT 1;")

    def write_snapshots(self, snapshots: list[MarketSnapshot], timestamp: str) -> None:
        if not snapshots:
            return
        with transaction() as cur:
            for snap in snapshots:
                cur.execute(
                    """
                    INSERT INTO goods
                        (goods_id, family, knife_type, skin_name, condition,
                         reference_price, image_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (goods_id) DO UPDATE SET
                        family          = EXCLUDED.family,
                        knife_type      = EXCLUDED.knife_type,
                        skin_name       = EXCLUDED.skin_name,
                        condition       = EXCLUDED.condition,
                        reference_price = EXCLUDED.reference_price,
                        image_url       = EXCLUDED.image_url
                    """,
                    (
                        snap.goods_id,
                        snap.family,
                        snap.knife_type,
                        snap.skin_name,
                        snap.condition,
                        snap.reference_price,
                        snap.image_url,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO snapshots
                        (ts, goods_id, price, listings, buy_orders, observed_orders)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ts, goods_id) DO UPDATE SET
                        price           = EXCLUDED.price,
                        listings        = EXCLUDED.listings,
                        buy_orders      = EXCLUDED.buy_orders,
                        observed_orders = EXCLUDED.observed_orders
                    """,
                    (
                        timestamp,
                        snap.goods_id,
                        snap.price,
                        snap.listings,
                        snap.buy_orders,
                        snap.observed_orders,
                    ),
                )

    def load_history_frame(self) -> pd.DataFrame:
        try:
            with transaction() as cur:
                cur.execute("""
                    SELECT
                        s.ts                    AS "Timestamp",
                        g.goods_id              AS "Goods ID",
                        g.family                AS "Family",
                        g.knife_type            AS "Knife Type",
                        g.skin_name             AS "Skin Name",
                        g.condition             AS "Condition",
                        s.price                 AS "Price",
                        s.listings              AS "Listings",
                        s.buy_orders            AS "Buy Orders",
                        g.reference_price       AS "Reference Price",
                        g.image_url             AS "Image URL",
                        s.observed_orders       AS "Observed Orders"
                    FROM snapshots s
                    JOIN goods g ON g.goods_id = s.goods_id
                    ORDER BY s.ts ASC;
                """)
                rows = cur.fetchall()
        except Exception as exc:
            message = redact_secrets(str(exc))
            print(f"PostgresStore.load_history_frame failed: {exc.__class__.__name__}: {message}")
            return self.empty_history_frame()

        if not rows:
            return self.empty_history_frame()

        return pd.DataFrame([dict(r) for r in rows]).reindex(columns=HISTORY_HEADERS)

    def record_run_summary(self, summary: ScrapeRunSummary) -> None:
        try:
            with transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO scraper_runs
                        (run_id, started_at, finished_at, backend, total_items,
                         success_count, failure_count, skipped_count, status, error_summary)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid4()),
                        summary.started_at,
                        summary.finished_at,
                        summary.storage_backend or "postgres",
                        summary.attempted,
                        summary.succeeded,
                        summary.failed,
                        summary.skipped,
                        summary.status,
                        "; ".join(summary.errors)[:500],
                    ),
                )
        except Exception as exc:
            message = redact_secrets(str(exc))
            print(f"PostgresStore.record_run_summary failed: {exc.__class__.__name__}: {message}")
