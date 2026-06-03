# AWS Deployment Readiness Audit

Audit of what must change to run the BUFF163 scraper on AWS as a scheduled
cloud job. **No runtime code changed in this phase** — this is analysis only.

## Current data flow

```
EventBridge (future)            python main.py
        │                              │
        ▼                              ▼
   (scheduler)  ──────────────▶  src/cli.py: main()
                                       │
                                       ▼
                            src/orchestrator.py: run()
                                       │
        ┌──────────────────────────────┼───────────────────────────┐
        ▼                              ▼                            ▼
  BuffPriceClient (src/client.py)   validation (src/validation.py)  ScrapeRunSummary
  - requests.Session                - price>0, listings>=0          (src/results.py)
  - retry+backoff+jitter (retry.py) - skip+log invalid              - log line + exit code
  - 403/404 fail fast
        │
        ▼
  discover_high_value_catalog → snapshots
        │
        ▼
  storage backend (src/storage/factory.py: STORAGE_BACKEND)
        ├── sheets   → Google Sheets (needs service-account creds)
        ├── sqlite   → local file (NOT cloud-suitable: ephemeral FS)
        └── postgres → DATABASE_URL, ON CONFLICT (ts,goods_id) upsert  ◀── cloud target
```

Entry point for headless runs: **`python main.py`** (`main.py` → `src/cli.py::main()`
→ `src/orchestrator.py::run()`). Exit code already cloud-safe
(`src/cli.py` uses `ScrapeRunSummary.exit_code()`: 0 success/partial/empty, 1 all-failed).

## AWS target architecture (primary)

| Component | AWS service | Notes |
|-----------|-------------|-------|
| Compute | **Lambda (container image)** | Python 3.11 base image `public.ecr.aws/lambda/python:3.11` |
| Image registry | **Amazon ECR** | private repo for the Lambda image |
| Schedule | **EventBridge Scheduler** | cron/rate expression, e.g. `rate(12 hours)` |
| Secrets | **AWS Secrets Manager** | `DATABASE_URL`, `BUFF_COOKIE`, (optional Google creds) |
| Logs | **CloudWatch Logs** | one-line run summary + structured errors |
| Storage | **existing PostgreSQL** | `STORAGE_BACKEND=postgres`, already on `main` |

## Required environment variables (Lambda)

| Variable | Required | Source | Purpose |
|----------|----------|--------|---------|
| `STORAGE_BACKEND=postgres` | yes | env | select cloud-safe backend |
| `DATABASE_URL` | yes | **Secrets Manager** | Postgres DSN |
| `BUFF_COOKIE` | recommended | **Secrets Manager** | avoid 403 from BUFF163 |
| `BUFF_REQUEST_TIMEOUT` | no (def 15) | env | per-request timeout |
| `BUFF_MAX_RETRIES` | no (def 3) | env | transient retry budget |
| `BUFF_BACKOFF_BASE_SECONDS` | no (def 1) | env | backoff base |
| `BUFF_HIGH_VALUE_PAGES` | recommended | env | bound runtime (pages/keyword) |
| `BUFF_MAX_GOODS_PER_RUN` | recommended | env | bound runtime (cap goods) |
| Google creds (`GSHEET_CREDS_JSON`) | only if sheets | Secrets Manager | NOT needed for postgres |

## Required secrets (Secrets Manager)

- `buff163/DATABASE_URL` — Postgres connection string.
- `buff163/BUFF_COOKIE` — BUFF163 session cookie (rotate periodically).
- (optional) `buff163/GSHEET_CREDS_JSON` — only if Sheets backend is ever used.

Never log these. Header build is isolated in `src/buff_http.py`; never printed.

## Lambda suitability

**Can it run headless?** Yes — `python main.py` with env set. No interactive input.

**Local-file dependence?**
- Postgres backend: **no local files required** (verified via
  `src/storage/factory.py` + `src/storage/postgres_store.py`).
- SQLite backend writes a local file (`BUFF_SQLITE_PATH`) — Lambda FS is
  ephemeral (`/tmp` only), so **do not use sqlite in Lambda**.
- `PageMetaCache` defaults to a CWD SQLite file; on Lambda only `/tmp` is
  writable. If page-meta caching is exercised, point it at `/tmp` (verify in
  Phase 3) — otherwise read-only-FS error.

**Google creds?** Optional — required only for `STORAGE_BACKEND=sheets`.
Postgres path does not import or need them.

**Runtime duration risk (Lambda 15-min hard limit):**
- Full catalog discovery (`BUFF_FULL_CATALOG=1`, many keywords × up to 60
  pages) can exceed 15 minutes → **not Lambda-safe** unbounded.
- Bounded run (seed goods ids and/or small `BUFF_HIGH_VALUE_PAGES`,
  `BUFF_MAX_GOODS_PER_RUN`) fits comfortably under 15 min.
- **Recommendation:** start on Lambda with a *bounded* run profile + 900 s
  timeout, 512–1024 MB memory. If the desired scope cannot finish under
  ~13 min with margin, fall back to **ECS Fargate scheduled task** (no
  duration limit). Do not switch to ECS unless bounded Lambda proves
  insufficient.

## Implementation status after Phases 3-8

- **Lambda handler:** implemented in `handler.py` as
  `handler.lambda_handler(event, context)`. It calls `src.orchestrator.run()`,
  returns a JSON-safe summary, redirects Lambda local-file defaults to `/tmp`,
  supports health-check mode, and redacts fatal error messages.
- **Container packaging:** implemented in `Dockerfile.lambda` with
  `CMD ["handler.lambda_handler"]`; `.dockerignore` excludes secrets, local
  DBs, test artifacts, docs, and cache files.
- **Secrets wiring:** implemented through `src/secrets.py`, `src/redaction.py`,
  and Terraform `*_SECRET_ARN` environment variables.
- **IaC:** implemented under `infra/aws/` for ECR, Lambda, IAM, CloudWatch Logs,
  and EventBridge Scheduler.
- **Observability:** `ScrapeRunSummary` provides structured response fields and
  a one-line CloudWatch-friendly run summary; health-check mode avoids real
  scraping.
- **Runbook:** `docs/aws-production-runbook.md` covers build, push, deploy,
  manual test, CloudWatch logs, PostgreSQL verification, update, and rollback.

## Remaining deployment validation

Before production use, verify:

1. `docker build -f Dockerfile.lambda -t buff163-lambda:test .` succeeds on a
   machine with Docker running.
2. `terraform -chdir=infra/aws fmt -check` and
   `terraform -chdir=infra/aws validate` pass after `terraform init`.
3. A Lambda health-check invocation succeeds with the real Secrets Manager ARNs.
4. A bounded real scrape finishes comfortably below Lambda's 900-second limit.
   If the desired scrape scope cannot fit with margin, use the documented ECS
   Fargate fallback.
