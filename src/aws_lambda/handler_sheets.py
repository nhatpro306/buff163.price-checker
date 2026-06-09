"""Optional Google Sheets writer for the free-tier Lambda.

Loaded lazily by static_site_handler.lambda_handler only when WRITE_SHEETS=1.
Keeps gspread / google-auth out of the cold path when the user does not opt in.

Reads service-account JSON from SSM Parameter Store. Never logs credentials.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

LOG = logging.getLogger(__name__)


def _read_ssm(client: Any, name: str) -> str:
    if not name:
        return ""
    try:
        out = client.get_parameter(Name=name, WithDecryption=True)
        return str((out.get("Parameter") or {}).get("Value") or "")
    except Exception as exc:  # noqa: BLE001 - boundary
        LOG.warning("ssm_get_failed param=%s type=%s", name, type(exc).__name__)
        return ""


def write_sheets(
    ssm_client: Any,
    rows: list[dict[str, Any]],
    iso_now: str,
) -> tuple[int, list[str]]:
    """Append snapshot rows to a target worksheet. Returns (saved_count, errors).

    Required env:
      SPREADSHEET_ID, WORKSHEET_NAME, GOOGLE_CREDS_SSM_PARAM (default /buff163/google-creds)
    """
    spreadsheet_id = os.getenv("SPREADSHEET_ID", "").strip()
    worksheet_name = os.getenv("WORKSHEET_NAME", "").strip()
    ssm_param = os.getenv("GOOGLE_CREDS_SSM_PARAM", "/buff163/google-creds").strip()

    if not spreadsheet_id or not worksheet_name:
        return 0, ["sheets_skipped_missing_SPREADSHEET_ID_or_WORKSHEET_NAME"]
    if not rows:
        return 0, []

    creds_json = _read_ssm(ssm_client, ssm_param)
    if not creds_json:
        return 0, ["sheets_skipped_missing_creds_in_ssm"]

    try:
        import gspread  # noqa: PLC0415 - optional dep
        from google.oauth2.service_account import Credentials  # noqa: PLC0415

        creds = Credentials.from_service_account_info(
            json.loads(creds_json),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(spreadsheet_id)
        worksheet = sheet.worksheet(worksheet_name)
        values = [
            [
                iso_now,
                row.get("knife_type"),
                row.get("family"),
                row.get("condition"),
                row.get("price_cny"),
                row.get("reference_price_cny"),
                row.get("listings"),
                row.get("source"),
            ]
            for row in rows
        ]
        worksheet.append_rows(values, value_input_option="RAW")
        return len(rows), []
    except Exception as exc:  # noqa: BLE001 - boundary
        return 0, [f"sheets_write_failed: {type(exc).__name__}"]
