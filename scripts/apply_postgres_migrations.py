#!/usr/bin/env python3
"""Apply pending PostgreSQL migrations from db/migrations/.

Usage:
    python scripts/apply_postgres_migrations.py

Requires: DATABASE_URL env var pointing to the target database.

Idempotent: each migration is tracked in schema_migrations and skipped
if already applied.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


def main() -> None:
    # Validate env before importing the client (gives a clear error message).
    if not os.getenv("DATABASE_URL", "").strip():
        print(
            "ERROR: DATABASE_URL is not set.\n"
            "Example: export DATABASE_URL=postgresql://user:password@host:5432/dbname",
            file=sys.stderr,
        )
        sys.exit(1)

    from src.db.postgres_client import applied_migrations, apply_migration_file

    already_applied = applied_migrations()
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    if not migration_files:
        print(f"No migration files found in {MIGRATIONS_DIR}.")
        return

    applied_now: list[str] = []
    skipped: list[str] = []

    for sql_file in migration_files:
        version = sql_file.stem
        if version in already_applied:
            skipped.append(version)
            continue
        print(f"Applying migration: {version} ...")
        try:
            apply_migration_file(str(sql_file))
        except Exception as exc:
            print(
                f"ERROR applying {version}: {exc.__class__.__name__}: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)
        applied_now.append(version)
        print(f"  OK: {version}")

    if skipped:
        print(f"Already applied (skipped): {', '.join(skipped)}")
    if applied_now:
        print(f"Applied {len(applied_now)} migration(s): {', '.join(applied_now)}")
    else:
        print("All migrations already applied. Nothing to do.")


if __name__ == "__main__":
    main()
