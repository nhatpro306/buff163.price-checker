from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"


def _psycopg2():
    try:
        import psycopg2
        import psycopg2.extras

        return psycopg2
    except ImportError as exc:
        raise ImportError(
            "psycopg2 is required for PostgreSQL storage. "
            "Install it with: pip install psycopg2-binary"
        ) from exc


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise ValueError(
            "DATABASE_URL environment variable is required for PostgreSQL storage. "
            "Set it from a secret manager or local environment file; never print or commit it."
        )
    return url


def get_connection() -> Any:
    pg = _psycopg2()
    return pg.connect(_database_url(), options="-c timezone=UTC")


@contextmanager
def transaction() -> Generator[Any, None, None]:
    pg = _psycopg2()
    conn = get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=pg.extras.RealDictCursor) as cur:
                yield cur
    finally:
        conn.close()


def apply_migration_file(sql_path: str) -> None:
    sql = Path(sql_path).read_text(encoding="utf-8")
    with transaction() as cur:
        cur.execute(sql)


def applied_migrations() -> set[str]:
    try:
        with transaction() as cur:
            cur.execute("SELECT version FROM schema_migrations ORDER BY version;")
            return {row["version"] for row in cur.fetchall()}
    except Exception:
        return set()


def migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(migrations_dir.glob("*.sql"))


def apply_pending_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    already_applied = applied_migrations()
    applied_now: list[str] = []
    for sql_file in migration_files(migrations_dir):
        version = sql_file.stem
        if version in already_applied:
            continue
        apply_migration_file(str(sql_file))
        applied_now.append(version)
    return applied_now
