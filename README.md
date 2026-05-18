# BUFF163 Price Checker

Track CS2 knife prices from BUFF163, store historical snapshots in Google Sheets or SQLite, and view market movement in a Streamlit dashboard.

The project has two user-facing entry points:

- `python main.py` runs the tracker.
- `streamlit run app.py` opens the dashboard.

`main.py` is intentionally small. Most real logic lives in `src/` so the code is easier to test and maintain.

## Features

- Collects CS2 knife prices, listing counts, buy orders, reference prices, and image URLs.
- Writes history to Google Sheets for scheduled production runs.
- Supports SQLite for local/offline testing.
- Uses optional CSGO Trader fallback data when BUFF direct collection is unavailable.
- Merges direct, fallback, and full-catalog snapshots without losing listing depth.
- Builds catalog, history, dashboard, signal, and optional forecast sheets.
- Provides a Streamlit dashboard for prices, conditions, charts, signals, and catalog views.
- Supports Discord and Telegram alerts.
- Runs scheduled collection through GitHub Actions.

## Tech Stack

- Python 3.11
- Streamlit
- Pandas / NumPy
- Altair
- Requests / HTTPX
- Google Sheets API through `gspread`
- SQLite
- Pytest, Ruff, Black, Mypy
- GitHub Actions

## Project Structure

```text
.
|-- main.py                    # CLI facade and backward-compatible exports
|-- app.py                     # Streamlit dashboard
|-- app_data_utils.py          # Dashboard data loading and cleanup helpers
|-- market_config.py           # Constants, sheet names, defaults, headers
|-- market_models.py           # MarketSnapshot dataclass
|-- market_utils.py            # Shared parsing, env, JSON, and image helpers
|-- src/
|   |-- cli.py                 # argparse command-line entry point
|   |-- orchestrator.py        # High-level tracker workflow
|   |-- settings.py            # Environment-driven search settings
|   |-- client.py              # Sync BUFF client and compatibility exports
|   |-- async_client.py        # Async BUFF client
|   |-- buff_http.py           # Shared BUFF headers, cookies, retry env helpers
|   |-- discovery.py           # Catalog/search discovery strategies
|   |-- page_parser.py         # BUFF goods-page HTML parser
|   |-- snapshots.py           # Snapshot construction helpers
|   |-- snapshot_merge.py      # Direct/fallback/full-catalog merge logic
|   |-- analysis.py            # Price analysis and signal classification
|   |-- etl.py                 # History normalization and schema migration
|   |-- alerts.py              # Discord/Telegram alert dispatch
|   |-- storage.py             # Compatibility facade and PageMetaCache
|   `-- storage/
|       |-- credentials.py     # Google credential loading
|       |-- sheets.py          # Google Sheets readers/writers
|       `-- sqlite.py          # SQLite persistence
|-- tests/                     # Unit tests for clients, parsing, ETL, merge logic, alerts
|-- .github/workflows/
|   |-- buff-tracker.yml       # Scheduled tracker run
|   |-- lint.yml               # Ruff, Black, Mypy, Pytest
|   `-- python-checks.yml      # Compile check
|-- requirements.txt
|-- pyproject.toml
|-- Dockerfile
`-- render.yaml
```

## Quick Start

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

## Local SQLite Mode

SQLite mode is useful when you want to test locally without Google Sheets credentials.

Run the tracker without writing to Google Sheets:

```powershell
$env:BUFF_WRITE_SQLITE = "1"
$env:BUFF_WRITE_SHEETS = "0"
$env:BUFF_SQLITE_PATH = "buff163.sqlite3"
python main.py
```

Run a no-network smoke test:

```powershell
$env:BUFF_WRITE_SQLITE = "1"
$env:BUFF_WRITE_SHEETS = "0"
$env:BUFF_SKIP_DIRECT = "1"
$env:BUFF_FALLBACK_CSGOTRADER = "0"
$env:BUFF_FULL_CATALOG = "0"
python main.py
```

Read SQLite data in the dashboard:

```powershell
$env:BUFF_READ_SQLITE = "1"
$env:BUFF_SQLITE_PATH = "buff163.sqlite3"
streamlit run app.py
```

## Google Sheets Setup

The tracker can load Google service account credentials from:

1. `GSHEET_CREDS_JSON`

   Full service account JSON stored as one environment variable.

2. Streamlit secrets

   Either `GSHEET_CREDS_JSON` or a `[gcp_service_account]` secrets block.

3. `credentials.json`

   Local service account file in the repo root. Do not commit this file.

Your service account must have access to the target spreadsheet.

Default spreadsheet name:

```text
BuffKnifeTracker
```

Override it with:

```powershell
$env:BUFF_SHEET_NAME = "YourSheetName"
```

## Environment Variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `BUFF_SHEET_NAME` | Google Sheet name or URL | `BuffKnifeTracker` |
| `GSHEET_CREDS_JSON` | Google service account JSON | none |
| `GSHEET_CREDS` | Legacy Google service account JSON fallback | none |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to local credential file | `credentials.json` fallback |
| `BUFF_COOKIE` | Optional BUFF browser cookie | none |
| `BUFF_MIN_PRICE_CNY` | Minimum tracked price | `0` |
| `BUFF_HIGH_VALUE_PAGES` | BUFF market pages scanned per keyword | `25` locally, `2` in GitHub Actions |
| `BUFF_TRACK_KEYWORDS` | Comma-separated knife keywords | all supported knife types |
| `BUFF_SEARCH_KEYWORDS` | Override search terms | derived from tracked keywords |
| `BUFF_EXPAND_FINISH_SEARCHES` | Search common finishes per knife category | `false` |
| `BUFF_SEED_GOODS_IDS` | Seed goods IDs for page expansion | none |
| `BUFF_MAX_GOODS_PER_RUN` | Optional cap for direct collection | none |
| `BUFF_SKIP_DIRECT` | Skip direct BUFF collection | `false` |
| `BUFF_FALLBACK_CSGOTRADER` | Enable CSGO Trader fallback | `false` |
| `BUFF_MIN_FALLBACK_SNAPSHOTS` | Fail if fallback returns too few rows | `0` |
| `BUFF_FULL_CATALOG` | Enable full-catalog scan | `false` |
| `BUFF_FULL_CATALOG_PAGES` | Full-catalog pages per keyword | `60` locally, `12` in GitHub Actions |
| `BUFF_ENABLE_FORECAST` | Generate forecast sheet | `false` in scheduled workflow |
| `BUFF_WRITE_SQLITE` | Write snapshots to SQLite | `false` |
| `BUFF_READ_SQLITE` | Dashboard reads SQLite instead of Sheets | `false` |
| `BUFF_SQLITE_PATH` | SQLite database path | `buff163.sqlite3` |
| `BUFF_UI_REFRESH_SEC` | Dashboard auto-refresh seconds | `900` |
| `BUFF_UI_CACHE_TTL_SEC` | Dashboard cache TTL seconds | `300` |
| `PAGE_META_CACHE_PATH` | Page metadata SQLite cache | `page_meta_cache.sqlite3` |
| `ALERT_DISCORD_WEBHOOK` | Discord alert webhook | none |
| `ALERT_TELEGRAM_TOKEN` | Telegram bot token | none |
| `ALERT_TELEGRAM_CHAT_ID` | Telegram chat/channel ID | none |

## Development Checks

Run these before opening or merging a pull request:

```powershell
python -m ruff check .
python -m black --check .
python -m mypy src main.py
python -m pytest
python -m compileall -q .
```

Useful CLI smoke checks:

```powershell
python main.py --help
python -c "from main import BuffPriceClient, SheetStore, csgotrader_snapshots; print('compat OK')"
```

## GitHub Actions

The repository has three workflows:

- `buff-tracker.yml`: scheduled tracker run.
- `lint.yml`: Ruff, Black, Mypy, and Pytest.
- `python-checks.yml`: compile check.

The tracker workflow runs twice per day:

- `00:00 JST`
- `12:00 JST`

Required or useful repository secrets:

- `GSHEET_CREDS_JSON`
- `GSHEET_CREDS`
- `BUFF_COOKIE`
- `ALERT_DISCORD_WEBHOOK`
- `ALERT_TELEGRAM_TOKEN`
- `ALERT_TELEGRAM_CHAT_ID`

Manual tracker runs are available from GitHub Actions through `workflow_dispatch`.

## Data Flow

```text
BUFF163 direct search
        |
        v
src/client.py + src/discovery.py
        |
        v
MarketSnapshot rows
        |
        +--> CSGO Trader fallback merge
        +--> full-catalog depth merge
        |
        v
Google Sheets or SQLite
        |
        v
Streamlit dashboard
```

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

Render runs:

```text
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
```

Set the same credentials and environment variables in Render.

## Docker

Build:

```bash
docker build -t buff163-price-checker .
```

Run:

```bash
docker run --rm -p 8501:8501 --env-file .env buff163-price-checker
```

## Learning Notes

Important concepts in this project:

- Data modeling: `MarketSnapshot` represents one normalized market observation.
- Separation of concerns: client, discovery, parsing, storage, merge logic, and UI live in separate modules.
- ETL: raw API/page data is extracted, normalized, merged, and loaded into Sheets or SQLite.
- Retry and rate-limit handling: BUFF requests use retry/backoff behavior for scheduled reliability.
- Testability: parsing and snapshot-building logic is separated from network calls, so it can be tested directly.
- Time-series analysis: historical prices and listing depth are used to produce dashboard summaries and signals.

## Security Notes

- Do not commit `credentials.json`, cookies, service account keys, or `.env` files.
- Store production secrets in GitHub Actions secrets, Streamlit secrets, or hosting provider environment variables.
- Rotate any Google service account key that was ever exposed publicly.

## Roadmap Ideas

- Add `.env.example` for easier local onboarding.
- Add screenshots of the Streamlit dashboard.
- Add integration tests for SQLite tracker runs.
- Improve dashboard error messages for missing credentials or sheet permissions.
- Add richer alert rules and per-skin alert configuration.
