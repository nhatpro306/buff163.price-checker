#!/usr/bin/env python3
"""Import price history from SQLite or CSV into PostgreSQL.

Usage:
    # From local SQLite file:
    python scripts/import_existing_data_to_postgres.py --sqlite buff163.sqlite3

    # From a CSV export (must match HISTORY_HEADERS column names):
    python scripts/import_existing_data_to_postgres.py --csv history_export.csv

Requires: DATABASE_URL env var.

Safety:
    - Uses ON CONFLICT DO NOTHING so duplicate rows are silently skipped.
    - Does NOT delete any existing data in PostgreSQL.
    - Run after apply_postgres_migrations.py.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _check_database_url() -> None:
    if not os.getenv("DATABASE_URL", "").strip():
        print(
            "ERROR: DATABASE_URL is not set.\n"
            "Set DATABASE_URL from a secret manager or local environment file; never print or commit it.",
            file=sys.stderr,
        )
        sys.exit(1)


def _load_from_sqlite(sqlite_path: str):
    from src.storage.sqlite import sqlite_load_history_frame

    path = Path(sqlite_path)
    if not path.exists():
        print(f"ERROR: SQLite file not found: {sqlite_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading history from SQLite: {sqlite_path}")
    df = sqlite_load_history_frame(sqlite_path)
    print(f"  Loaded {len(df)} rows.")
    return df


def _load_from_csv(csv_path: str):
    import pandas as pd

    path = Path(csv_path)
    if not path.exists():
        print(f"ERROR: CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading history from CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"  Loaded {len(df)} rows.")
    return df


def _build_market_snapshots(df) -> list:
    import math

    from market_models import MarketSnapshot

    snapshots_by_ts: dict[str, list] = {}
    skipped = 0

    for _, row in df.iterrows():
        goods_id = str(row.get("Goods ID", "")).strip()
        ts = str(row.get("Timestamp", "")).strip()
        if not goods_id or not ts:
            skipped += 1
            continue

        price = row.get("Price")
        try:
            price_f = float(price)
            if math.isnan(price_f):
                price_f = 0.0
        except (TypeError, ValueError):
            price_f = 0.0

        snap = MarketSnapshot(
            goods_id=goods_id,
            family=str(row.get("Family", "") or ""),
            skin_name=str(row.get("Skin Name", "") or ""),
            condition=str(row.get("Condition", "Unknown") or "Unknown"),
            price=price_f,
            listings=int(float(row.get("Listings") or 0)),
            buy_orders=int(float(row.get("Buy Orders") or 0)),
            reference_price=(
                float(row.get("Reference Price"))
                if row.get("Reference Price") not in (None, "", float("nan"))
                else None
            ),
            image_url=str(row.get("Image URL", "") or ""),
            observed_orders=int(float(row.get("Observed Orders") or 0)),
        )
        snapshots_by_ts.setdefault(ts, []).append(snap)

    if skipped:
        print(f"  Skipped {skipped} rows with missing goods_id or timestamp.")

    return snapshots_by_ts


def _import_to_postgres(snapshots_by_ts: dict) -> None:
    from src.db.postgres_client import transaction

    total_rows = sum(len(v) for v in snapshots_by_ts.values())
    print(f"Importing {total_rows} snapshot rows across {len(snapshots_by_ts)} timestamps ...")

    inserted = 0
    skipped = 0

    with transaction() as cur:
        for ts, snapshots in snapshots_by_ts.items():
            for snap in snapshots:
                cur.execute(
                    """
                    INSERT INTO goods
                        (goods_id, family, knife_type, skin_name, condition,
                         reference_price, image_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (goods_id) DO NOTHING
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
                    ON CONFLICT (ts, goods_id) DO NOTHING
                    """,
                    (
                        ts,
                        snap.goods_id,
                        snap.price,
                        snap.listings,
                        snap.buy_orders,
                        snap.observed_orders,
                    ),
                )
                # Track inserts via rowcount (1 = inserted, 0 = conflict-skipped)
                if cur.rowcount == 1:
                    inserted += 1
                else:
                    skipped += 1

    print(f"  Inserted: {inserted}  |  Skipped (already existed): {skipped}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import price history from SQLite or CSV into PostgreSQL."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sqlite", metavar="PATH", help="Path to local SQLite history file.")
    source.add_argument(
        "--csv", metavar="PATH", help="Path to CSV export (HISTORY_HEADERS columns)."
    )
    args = parser.parse_args()

    _check_database_url()

    if args.sqlite:
        df = _load_from_sqlite(args.sqlite)
    else:
        df = _load_from_csv(args.csv)

    if df.empty:
        print("Source is empty. Nothing to import.")
        return

    snapshots_by_ts = _build_market_snapshots(df)
    _import_to_postgres(snapshots_by_ts)
    print("Import complete.")


if __name__ == "__main__":
    main()
