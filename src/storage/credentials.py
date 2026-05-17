from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from google.oauth2 import service_account


def resolve_credentials_path() -> Path:
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    # Local fallback for development only. Production should use secret JSON
    # env vars such as GSHEET_CREDS_JSON, not committed credential files.
    candidates = [
        Path("credentials.json"),
        Path(__file__).resolve().parent / "credentials.json",
        Path(__file__).resolve().parent.parent / "credentials.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError("credentials.json was not found.")


def credentials_from_info(info: dict[str, Any], scope: list[str]) -> service_account.Credentials:
    normalized = dict(info)
    private_key = normalized.get("private_key")
    if isinstance(private_key, str):
        normalized["private_key"] = private_key.replace("\\n", "\n").replace("\r\n", "\n")
    return service_account.Credentials.from_service_account_info(normalized, scopes=scope)


def load_google_credentials(scope: list[str]) -> service_account.Credentials:
    env_json_keys = [
        "GSHEET_CREDS_JSON",
        "GSHEET_CREDS",
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
        "GOOGLE_CREDENTIALS_JSON",
    ]
    for key in env_json_keys:
        raw_json = os.getenv(key)
        if raw_json:
            # GitHub Actions and most hosts work best with the whole service
            # account JSON stored as one secret environment variable.
            return credentials_from_info(json.loads(raw_json), scope)

    try:
        import streamlit as st

        # Streamlit Cloud stores secrets separately from normal environment
        # variables, so the dashboard supports both deployment styles.
        for key in ("GSHEET_CREDS_JSON", "GSHEET_CREDS", "GOOGLE_CREDENTIALS_JSON"):
            if key in st.secrets:
                return credentials_from_info(json.loads(str(st.secrets[key])), scope)
        if "gcp_service_account" in st.secrets:
            return credentials_from_info(dict(st.secrets["gcp_service_account"]), scope)
    except Exception:
        pass

    return service_account.Credentials.from_service_account_file(
        str(resolve_credentials_path()),
        scopes=scope,
    )
