# BUFF163 Price Checker

A production-style Python + Streamlit project that tracks CS2 knife market prices from BUFF163, stores historical snapshots, and presents decision-ready analytics in a dashboard.

## Project Overview

`BUFF163 Price Checker` is an end-to-end data pipeline and analytics app:

- Ingests market data from BUFF163 (with optional CSGOTrader fallback).
- Normalizes and stores historical records in Google Sheets or SQLite.
- Rebuilds analytics tables (catalog, dashboard, signals, optional forecast).
- Serves an interactive Streamlit interface for monitoring trends and liquidity.

This project is designed to demonstrate practical skills relevant to Data Analyst and Cloud Engineer roles: data ingestion, ETL reliability, scheduling, storage design, and reporting UI.

## Features

- Automated collection of CS2 knife prices, listings, and buy orders.
- Dual storage mode: Google Sheets (cloud-first) or SQLite (local/offline).
- Scheduled automation via GitHub Actions (twice daily + manual trigger).
- Fallback source support when direct BUFF coverage is incomplete.
- Listing-depth backfill from latest history for fallback-only rows.
- Streamlit dashboard with:
  - knife family and condition filtering
  - price trend charts
  - listings / buy-order indicators
  - optional live listing refresh using BUFF cookie
- Migration helpers for history schema evolution.
- Lightweight unit tests for merge and fallback behavior.

## Tech Stack

- Python 3.11
- Streamlit
- Pandas
- NumPy
- Altair
- Requests
- Google Sheets API (`gspread`, `google-auth`)
- SQLite
- GitHub Actions

## Project Structure

```text
.
|-- app.py
|-- main.py
|-- app_data_utils.py
|-- market_config.py
|-- market_models.py
|-- market_utils.py
|-- src/
|   |-- __init__.py
|   |-- scraper.py       # scraper-related exports
|   |-- data_loader.py   # storage and history loader exports
|   |-- analysis.py      # analysis exports
|   `-- alerts.py        # signal/alert exports
|-- tests/
|   `-- test_snapshot_merge.py
`-- .github/workflows/
```

## Screenshots

Add screenshots to visually strengthen your portfolio presentation:

- `docs/screenshots/dashboard-overview.png` - main dashboard page
- `docs/screenshots/family-condition-view.png` - family and condition drill-down
- `docs/screenshots/history-trend-chart.png` - price trend visualization
- `docs/screenshots/github-actions-run.png` - scheduled workflow execution

Example markdown once images are added:

```md
![Dashboard Overview](docs/screenshots/dashboard-overview.png)
![Condition Drill-Down](docs/screenshots/family-condition-view.png)
![Trend Chart](docs/screenshots/history-trend-chart.png)
![GitHub Actions Run](docs/screenshots/github-actions-run.png)
```

## Setup Instructions

### 1. Clone repository

```bash
git clone https://github.com/nhatpro306/buff163.price-checker.git
cd buff163.price-checker
```

### 2. Create virtual environment

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure credentials and environment

Use one of these for Google Sheets access:

- `GSHEET_CREDS_JSON` (recommended)
- Streamlit secrets (`[gcp_service_account]`)
- local `credentials.json` (never commit)

Common environment variables:

- `BUFF_SHEET_NAME` (default: `BuffKnifeTracker`)
- `BUFF_COOKIE` (optional, for richer BUFF access/live listing)
- `BUFF_WRITE_SQLITE` / `BUFF_READ_SQLITE`
- `BUFF_SQLITE_PATH` (default: `buff163.sqlite3`)
- `BUFF_FALLBACK_CSGOTRADER` (enable fallback source)

## How to Run Locally

### Run tracker pipeline

```bash
python main.py
```

### Run dashboard

```bash
streamlit run app.py
```

### Optional: SQLite-only local mode

```bash
# write snapshots to sqlite
BUFF_WRITE_SQLITE=1
BUFF_WRITE_SHEETS=0
python main.py

# read dashboard data from sqlite
BUFF_READ_SQLITE=1
streamlit run app.py
```

PowerShell equivalent:

```powershell
$env:BUFF_WRITE_SQLITE="1"
$env:BUFF_WRITE_SHEETS="0"
python main.py

$env:BUFF_READ_SQLITE="1"
streamlit run app.py
```

## Docker

Build image:

```bash
docker build -t buff163-price-checker .
```

Run container:

```bash
docker run --rm -p 8501:8501 buff163-price-checker
```

Open in browser:

```text
http://localhost:8501
```

If you need environment variables (for example `GSHEET_CREDS_JSON`, `BUFF_COOKIE`, or SQLite flags), pass them at runtime:

```bash
docker run --rm -p 8501:8501 \
  -e GSHEET_CREDS_JSON='{"type":"service_account", ...}' \
  -e BUFF_COOKIE='your_cookie_here' \
  buff163-price-checker
```

## Business Value

This project provides a practical market-intelligence workflow:

- **Price monitoring**: tracks high-value knife price movement over time.
- **Liquidity visibility**: monitors listings and buy-order pressure as supply/demand signals.
- **Decision support**: summarizes trends for buy/sell watch decisions.
- **Automation ROI**: replaces manual checks with scheduled, repeatable data collection.
- **Operational resilience**: fallback data source and backfill logic reduce missing-day risk.

For portfolio review, this demonstrates ownership of the full lifecycle: ingest -> transform -> store -> visualize -> automate.

## Future Improvements

- Expand tests to cover parsing, migration, and UI data-prep edge cases.
- Add lint/type-check CI (`ruff`, `black`, `mypy`) for engineering quality.
- Add alerting integrations (Discord/Email) for threshold-based events.
- Add data-quality checks and anomaly detection on sudden price shifts.
- Add architecture diagram and data dictionary in `/docs`.

## Live Demo

[Open Streamlit App](https://buff163price-checker.streamlit.app/)
