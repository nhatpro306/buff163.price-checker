# Scraper Reference Patterns

What we studied in proven scraping projects, what we borrowed, what we rejected,
and why this project does **not** migrate to a heavyweight framework.

## Repositories inspected

| Repo | License | What we looked at |
|------|---------|-------------------|
| [scrapy/scrapy](https://github.com/scrapy/scrapy) | BSD-3 | RetryMiddleware, HttpCacheMiddleware, downloader/spider/pipeline separation, stats collector |
| [apify/crawlee-python](https://github.com/apify/crawlee-python) | Apache-2.0 | Crawler run lifecycle, request handler model, failed-request handling, run statistics |
| [scrapy-plugins/scrapy-deltafetch](https://github.com/scrapy-plugins/scrapy-deltafetch) | BSD-3 | Delta crawl / "seen item" fingerprinting to skip already-seen data |
| [jd/tenacity](https://github.com/jd/tenacity) | Apache-2.0 | Exponential backoff, retry-only-on-transient, stop conditions, jitter |
| [requests-cache/requests-cache](https://github.com/requests-cache/requests-cache) | BSD-2 | Optional transparent HTTP cache, opt-in/disabled-by-default usage |
| [encode/httpx](https://github.com/encode/httpx) | BSD-3 | Timeout model, explicit client abstraction; requests-vs-httpx tradeoff |

> No third-party code was vendored or pasted. All new modules are original
> project code. Patterns above are design inspiration only, so attribution
> beyond this table is not required by any of the listed licenses.

## What we borrowed

### From Tenacity — retry policy (`src/retry.py`)
- **Retry only transient failures.** `RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}`
  plus `requests.Timeout` / `requests.ConnectionError`. Everything else
  (403, 404, bad business data) fails fast.
- **Exponential backoff with full jitter.** `compute_backoff` returns a random
  delay in `[0, min(cap, base*2**attempt)]` so parallel scheduled runs do not
  synchronize their retries (thundering herd).
- **Bounded attempts.** `BUFF_MAX_RETRIES` (default 3). No infinite retry.

### From Scrapy — layer separation
The scraper already separates concerns; we kept and sharpened it:
- request/transport: `src/client.py` (+ `src/buff_http.py` headers, `src/retry.py`)
- parsing: `src/page_parser.py`, `src/snapshots.py`, `src/etl.py`
- validation: `src/validation.py` (new)
- orchestration: `src/orchestrator.py`
- storage: `src/storage/*` (sheets / sqlite / postgres backends)

Scrapy's **stats collector** inspired `ScrapeRunSummary` (`src/results.py`):
one structured object summarizing a run.

### From Crawlee — run summary + exit semantics
A single end-of-run summary (`ScrapeRunSummary`) maps to a one-line log and a
process exit code, the way Crawlee surfaces run statistics. See
`docs/scraper-cloud-readiness.md`.

### From scrapy-deltafetch — duplicate safety (already present)
Deltafetch skips requests whose fingerprint was already seen. This project's
equivalent already exists at the **storage** layer:
- SQLite: `UNIQUE(ts, goods_id)` + `INSERT ... ON CONFLICT(ts, goods_id) DO UPDATE`
- Postgres: `ON CONFLICT (ts, goods_id) DO UPDATE`

So repeated scheduler runs **upsert** instead of creating duplicate rows. We
documented this rather than adding a second fingerprint store.

## What we rejected (too heavy / not needed)

- **Migrating to Scrapy or Crawlee.** This scraper hits a handful of BUFF163
  endpoints for a curated keyword/seed set. A full framework (reactor, spider
  classes, signals, scheduler, middlewares) would add large dependencies and
  concept overhead for no real gain. A `requests` client + retry + validation +
  pipeline is smaller, easier for one maintainer, and already covers the needs.
- **A separate deltafetch fingerprint DB.** Storage-layer upsert already gives
  idempotent repeated runs. A second store would be redundant state to keep.
- **Migrating from `requests` to `httpx`.** `httpx`'s big wins (async, HTTP/2)
  are not needed here; an `AsyncBuffPriceClient` already exists for the async
  path. The sync `requests` client is fine. httpx's *timeout clarity* is matched
  by always passing an explicit `timeout` on every request.
- **requests-cache as a production dependency.** A response cache in a scheduled
  price scraper would serve stale prices and risks caching authenticated
  responses. Left as an **opt-in dev-only** idea (`BUFF_HTTP_CACHE_ENABLED`,
  disabled by default, not yet implemented).

## What we implemented with small changes

- `src/retry.py` — error classification + backoff/jitter (new, ~60 lines).
- `src/results.py` — `ScrapeItemResult`, `ScrapeRunSummary` (new).
- `src/validation.py` — business-data validation (new).
- `src/client.py::_get` — rewritten to retry transient errors with backoff +
  jitter (replaces urllib3 `Retry` + ad-hoc 429 loop).
- `src/orchestrator.py` — validate snapshots before storage; build a run
  summary; emit a single summary log line.
- `src/cli.py` — cloud-safe exit code derived from the run summary.
