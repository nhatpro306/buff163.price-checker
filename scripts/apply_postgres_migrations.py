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


def main() -> None:
    # Validate env before importing the client (gives a clear error message).
    if not os.getenv("DATABASE_URL", "").strip():
        print(
            "ERROR: DATABASE_URL is not set.\n"
            "Set DATABASE_URL from a secret manager or local environment file; never print or commit it.",
            file=sys.stderr,
        )
        sys.exit(1)

    from src.db.postgres_client import MIGRATIONS_DIR, apply_pending_migrations, migration_files

    files = migration_files()

    if not files:
        print(f"No migration files found in {MIGRATIONS_DIR}.")
        return

    try:
        applied_now = apply_pending_migrations()
    except Exception as exc:
        print(f"ERROR applying migrations: {exc.__class__.__name__}", file=sys.stderr)
        sys.exit(1)

    if applied_now:
        print(f"Applied {len(applied_now)} migration(s): {', '.join(applied_now)}")
    else:
        print("All migrations already applied. Nothing to do.")


if __name__ == "__main__":
    main()
