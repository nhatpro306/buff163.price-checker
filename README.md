# BUFF163 Price Tracker

This project has two parts:

1. `main.py`
Collects BUFF163 prices and writes history, dashboard data, signals, and forecasts into Google Sheets.

2. `app.py`
Runs a Streamlit dashboard that reads the same Google Sheet and shows price changes over time.

## Local run

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the tracker:

```powershell
python main.py
```

Run Streamlit:

```powershell
streamlit run app.py
```

## Google Sheets credentials

The app supports three credential sources:

1. `GSHEET_CREDS_JSON`
   Full Google service account JSON as a single environment variable.

2. Streamlit secrets
   Either:
   - `GSHEET_CREDS_JSON`
   - `gcp_service_account`

3. `credentials.json`
   Local file in the repo root.

## GitHub Actions

The included workflow runs `main.py` on a schedule and writes fresh price data into Google Sheets.

Required repository secrets:

- `GSHEET_CREDS`
- `BUFF_COOKIE` if BUFF starts requiring authenticated access for your requests

## Streamlit Cloud deployment

Connect this GitHub repo to Streamlit Cloud and set secrets there.

Recommended Streamlit secrets:

```toml
BUFF_SHEET_NAME = "BuffKnifeTracker"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

App entrypoint:

- `app.py`

## Result

- GitHub Actions updates the Google Sheet on a schedule.
- Streamlit reads the Google Sheet and shows the latest price and history.
- When the sheet changes, the Streamlit app reflects the new data.
