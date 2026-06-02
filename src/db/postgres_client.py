from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator


if TYPE_CHECKING:
    import psycopg2.extensions
    import psycopg2.extras


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
            "Set it to a valid PostgreSQL connection string, e.g.: "
            "postgresql://user:password@host:5432/dbname"
        )
    return url


def get_connection() -> Any:
    pg = _psycopg2()
    return pg.connect(_database_url())


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
    sql = open(sql_path, encoding="utf-8").read()
    with transaction() as cur:
        cur.execute(sql)


def applied_migrations() -> set[str]:
    try:
        with transaction() as cur:
            cur.execute("SELECT version FROM schema_migrations ORDER BY version;")
            return {row["version"] for row in cur.fetchall()}
    except Exception:
        return set()
