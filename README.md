# BUFF163 Price Checker

A Python + Streamlit project for tracking CS2 knife prices from BUFF163, storing price history in Google Sheets or SQLite, and visualizing market movement in a dashboard.

The project has two main entry points:

- `main.py` collects market data, writes history, rebuilds catalog sheets, generates signals, and optionally creates forecasts.
- `app.py` runs the Streamlit dashboard for browsing knife prices, listings, buy orders, history charts, condition catalogs, forecasts, and full catalog data.

## Live Demo

Check the Streamlit app here after deployment:

[Open BUFF163 Price Checker](https://buff163price-checker.streamlit.app/)

## Features

- Tracks CS2 knife market prices from BUFF163.
- Stores historical snapshots in Google Sheets.
- Supports local SQLite storage for offline or lightweight workflows.
- Provides a Streamlit dashboard with price history, listing counts, condition filtering, and catalog tables.
- Supports scheduled GitHub Actions runs.
- Includes optional fallback data from CSGO Trader.
- Backfills fallback listing and buy-order depth from latest known history to reduce missing listing days.
- Supports optional forecast generation.
- Can be deployed to Streamlit Cloud or Render.

## Tech Stack

- Python 3.11
- Streamlit
- Pandas
- NumPy
- Altair
- Requests
- Google Sheets API via `gspread`
- SQLite
- GitHub Actions

## Project Structure

```text
.
|-- app.py                  # Streamlit dashboard
|-- app_data_utils.py       # Data loading and cleaning helpers for the app
|-- main.py                 # Tracker orchestration, sheet writes, analysis, and CLI entrypoint
|-- market_config.py        # Shared constants, sheet names, headers, and default knife lists
|-- market_models.py        # Shared dataclasses such as MarketSnapshot
|-- market_utils.py         # Parsing, env flag, ID, JSON cache, and image helper functions
|-- requirements.txt        # Python dependencies
|-- runtime.txt             # Python runtime for hosting platforms
|-- render.yaml             # Render deployment config
|-- tests/
|   `-- test_snapshot_merge.py
`-- .github/workflows/
    `-- buff-tracker.yml    # Scheduled GitHub Actions tracker run
```

## Local Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the tracker:

```powershell
python main.py
```

Run the dashboard:

```powershell
streamlit run app.py
```

## Google Sheets Setup

The app supports three credential sources:

1. `GSHEET_CREDS_JSON`

   Full Google service account JSON stored as one environment variable.

2. Streamlit secrets

   Use either `GSHEET_CREDS_JSON` or a `[gcp_service_account]` secrets block.

3. `credentials.json`

   Local service account file in the repo root. This file is ignored by Git and should not be committed.

Your Google service account must have access to the target spreadsheet.

Default spreadsheet name:

```text
BuffKnifeTracker
```

You can override it with:

```powershell
$env:BUFF_SHEET_NAME = "YourSheetName"
```

## Common Environment Variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `BUFF_SHEET_NAME` | Google Sheet name | `BuffKnifeTracker` |
| `GSHEET_CREDS_JSON` | Service account JSON string | none |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to local credential file | `credentials.json` fallback |
| `BUFF_COOKIE` | Optional BUFF session cookie for authenticated requests | none |
| `BUFF_MIN_PRICE_CNY` | Minimum price filter | `0` |
| `BUFF_HIGH_VALUE_PAGES` | Number of BUFF market pages to scan | `25` in code, `2` in GitHub Actions |
| `BUFF_FULL_CATALOG` | Enable full catalog scan | `false` |
| `BUFF_FULL_CATALOG_PAGES` | Number of full catalog pages to scan | `60` in code, `12` in GitHub Actions |
| `BUFF_FALLBACK_CSGOTRADER` | Enable fallback price source when direct BUFF misses items | `false` |
| `BUFF_MIN_FALLBACK_SNAPSHOTS` | Minimum fallback rows required, fail run if lower | `0` |
| `BUFF_ENABLE_FORECAST` | Enable forecast sheet generation | `false` in scheduled workflow |
| `BUFF_WRITE_SQLITE` | Write snapshots to SQLite | `false` |
| `BUFF_READ_SQLITE` | Read dashboard data from SQLite | `false` |
| `BUFF_SQLITE_PATH` | SQLite database path | `buff163.sqlite3` |
| `BUFF_UI_REFRESH_SEC` | Streamlit auto-refresh interval | `900` |
| `BUFF_UI_CACHE_TTL_SEC` | Streamlit cache TTL | `300` |

## SQLite Mode

SQLite is useful when you want to test locally without Google Sheets.

Write tracker data to SQLite:

```powershell
$env:BUFF_WRITE_SQLITE = "1"
$env:BUFF_WRITE_SHEETS = "0"
$env:BUFF_SQLITE_PATH = "buff163.sqlite3"
python main.py
```

Read dashboard data from SQLite:

```powershell
$env:BUFF_READ_SQLITE = "1"
$env:BUFF_SQLITE_PATH = "buff163.sqlite3"
streamlit run app.py
```

## GitHub Actions

The workflow in `.github/workflows/buff-tracker.yml` runs twice per day:

- `00:00 JST`
- `12:00 JST`

Required repository secrets:

- `GSHEET_CREDS_JSON` recommended, full service-account JSON string
- `GSHEET_CREDS` optional fallback for legacy setups
- `BUFF_COOKIE` optional, useful if BUFF requires authenticated access

Manual runs are also supported from the GitHub Actions tab through `workflow_dispatch`.

## Fallback Listing Backfill

When direct BUFF scanning misses some knives, fallback prices can still be collected from CSGO Trader.

Because fallback does not provide live listing depth, the tracker now reuses the latest known `Listings` and `Buy Orders` from your existing history for matching `Family + Condition` keys. This keeps recent rows more complete while still avoiding extra BUFF API requests that can increase rate-limit risk.

## Streamlit Cloud Deployment

Use `app.py` as the Streamlit entry point.

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

## Render Deployment

This repository includes `render.yaml`.

Render uses:

```text
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
```

Set the same credentials and environment variables in the Render dashboard.

## How The Data Flow Works

```text
BUFF163 / fallback source
        |
main.py tracker
        |
Google Sheets or SQLite
        |
app.py Streamlit dashboard
        |
Charts, tables, signals, and forecasts
```

## Learning Notes

Important programming concepts used in this project:

- API clients: `BuffPriceClient` wraps HTTP requests, retry behavior, headers, cookies, and parsing.
- Data modeling: `MarketSnapshot` uses a dataclass to represent one clean market record.
- ETL pipeline: data is extracted from APIs, transformed into normalized rows, and loaded into Sheets or SQLite.
- Caching: Streamlit cache decorators reduce repeated network and Google Sheets calls.
- Separation of concerns: `main.py` handles collection and analysis; `app.py` handles UI; `app_data_utils.py` handles reusable data preparation.
- Time series basics: historical prices are grouped over time and can be used for simple forecasting.

## Security Notes

- Do not commit `credentials.json`, `credentials.json.bak`, cookies, or service account keys.
- Store production secrets in GitHub Actions secrets, Streamlit secrets, or your hosting provider's environment settings.
- If a credential file was ever committed publicly, rotate that service account key in Google Cloud.

## Roadmap Ideas

- Add automated tests for data cleaning and parsing.
- Add a `.env.example` file for easier onboarding.
- Add price alert notifications through Discord, email, or Telegram.
- Add clearer error messages for missing Google Sheets permissions.
- Add deployment screenshots to make the GitHub page more visual.
