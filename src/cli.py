from __future__ import annotations

import argparse

from src.orchestrator import run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migrate-only", action="store_true")
    args = parser.parse_args()
    try:
        run(migrate_only=args.migrate_only)
    except FileNotFoundError as exc:
        print(f"Startup error: {exc}")
        print(
            "Provide Google credentials via `GSHEET_CREDS_JSON` or place `credentials.json` "
            "in the project root. For local SQLite-only viewing, use Streamlit with "
            "`BUFF_READ_SQLITE=1` and `BUFF_SQLITE_PATH`."
        )
        raise SystemExit(1)
    except Exception as exc:
        print(f"Unhandled error: {exc.__class__.__name__}: {exc}")
        raise SystemExit(1)
