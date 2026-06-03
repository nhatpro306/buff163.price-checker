# Scraper Cloud Readiness

How the BUFF163 scraper behaves when run on a schedule (GitHub Actions / cron /
container), and how to operate it safely.

## How it works (high level)

1. `main.py` → `src/cli.py::main()` parses args and calls `src/orchestrator.py::run()`.
2. `run()` builds a `BuffPriceClient`, discovers high-value snapshots
   (`discover_high_value_catalog`), optionally merges a CSGOTrader fallback and a
   full-catalog pass.
3. Snapshots are **validated** (`src/validation.py`); invalid ones are skipped.
4. Valid snapshots are written to the configured storage backend
   (Google Sheets / SQLite / Postgres).
5. A `ScrapeRunSummary` is finalized, logged as one line, and turned into a
   process exit code.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `STORAGE_BACKEND` | `sheets` | `sheets` \| `sqlite` \| `postgres` |
| `DATABASE_URL` | — | Postgres DSN (only when backend = postgres). **Secret.** |
| `BUFF_SQLITE_PATH` | `buff163.sqlite3` | SQLite file path |
| `BUFF_SHEET_NAME` | `BuffKnifeTracker` | Target spreadsheet |
| `BUFF_REQUEST_TIMEOUT` | `15` | Per-request timeout (seconds) |
| `BUFF_MAX_RETRIES` | `3` | Extra attempts after first try (transient only) |
| `BUFF_BACKOFF_BASE_SECONDS` | `1` | Base for exponential backoff w/ jitter |
| `BUFF_HTTP_CACHE_ENABLED` | `false` | Dev-only HTTP cache flag (reserved, not yet implemented) |
| `BUFF_SEED_GOODS_IDS` | — | Comma-separated seed goods_id values |
| `BUFF_COOKIE` | — | BUFF163 auth cookie. **Secret.** Without it, requests may 403. |

Secrets (`DATABASE_URL`, `BUFF_COOKIE`, Google credentials) must come from
GitHub Secrets / a secrets manager — never committed.

## Retry behavior

Retried (with exponential backoff + full jitter, up to `BUFF_MAX_RETRIES`):
- `requests.Timeout`
- `requests.ConnectionError`
- HTTP `429, 500, 502, 503, 504`

**Not** retried (fail fast):
- HTTP `403` (auth/blocked), `404` (missing)
- Invalid goods_id / malformed business data after a successful response

Backoff per attempt: random delay in `[0, min(8.0, base * 2**attempt)]`.

## Validation behavior

Before storage each snapshot must satisfy:
- non-empty `goods_id`
- `price` is a number `> 0`
- `listings` is an integer `>= 0`
- non-empty `skin_name`

Invalid snapshots are **skipped** (counted as `skipped`, logged via
`debug_log`), never stored, and never abort the run.

## Duplicate safety

Repeated scheduled runs are **idempotent at the storage layer**:
- SQLite: `UNIQUE(ts, goods_id)` + `ON CONFLICT(ts, goods_id) DO UPDATE`
- Postgres: `ON CONFLICT (ts, goods_id) DO UPDATE`

A retry that re-writes the same `(timestamp, goods_id)` updates the existing row
instead of inserting a duplicate. No schema change was needed.

## Logging policy

Logs include: run start, snapshot counts, retry sleeps (implicit), per-item
skip reasons (`debug_log`), and the final summary line:

```
Scraper run finished: status=partial_success attempted=6 succeeded=4 failed=2 skipped=0 duration_seconds=18.4
```

Logs must **never** contain: cookies, CSRF tokens, `DATABASE_URL`, passwords,
full request headers, or other secret env values. Header construction lives in
`src/buff_http.py` and is never logged.

## Exit codes (cloud-safe)

| Outcome | Exit code |
|---------|-----------|
| All attempted items succeeded | 0 |
| Partial success (>= 1 item succeeded) | 0 |
| Nothing to scrape (attempted = 0) | 0 |
| Every attempted item failed | 1 |
| Fatal config / startup error | 1 |

No infinite retries; every request has a timeout; runs terminate.

## Commands

```bash
# Local run (SQLite, no Google Sheets)
STORAGE_BACKEND=sqlite BUFF_WRITE_SQLITE=1 python main.py

# Scheduled / cloud run (storage from env / secrets)
python main.py

# Tests (no network — all HTTP is mocked)
pytest -q

# Static checks
python -m compileall .
ruff check .
```

## Deployment checklist

- [ ] Secrets set in the runner (`BUFF_COOKIE`, `DATABASE_URL` or Google creds).
- [ ] `STORAGE_BACKEND` matches the intended store.
- [ ] `BUFF_REQUEST_TIMEOUT` / `BUFF_MAX_RETRIES` sane for the schedule.
- [ ] `BUFF_HTTP_CACHE_ENABLED=false` in CI/cloud.
- [ ] Schedule avoids overlapping runs (e.g. concurrency guard in the workflow).
- [ ] Verify exit code wiring: a workflow step failure should reflect exit 1.

## Known limitations

- `BUFF_HTTP_CACHE_ENABLED` is reserved but not yet implemented (dev-only idea).
- Validation runs on the final merged snapshot set; the streaming `on_snapshot`
  SQLite writer (used in `BUFF_WRITE_SQLITE` + non-sheets mode) writes during
  discovery before validation. Storage upsert keeps this safe, but a malformed
  streamed row could be written and later corrected by the validated pass.
- No proxy rotation / anti-bot handling by design. If BUFF163 returns 403,
  refresh `BUFF_COOKIE`.
- The run summary counts the final snapshot set, not every HTTP request made
  during discovery.
