# AWS Lambda Entrypoint

`handler.lambda_handler` lets the scraper run inside AWS Lambda while the local
CLI (`python main.py`) keeps working unchanged.

## How it works

```
EventBridge Scheduler → Lambda → handler.lambda_handler(event, context)
                                        │
                                        ▼
                                 src.orchestrator.run()   (same code as CLI)
                                        │
                                        ▼
                                 ScrapeRunSummary → JSON result
```

- Thin wrapper: all scrape, retry, validation, and storage logic is reused from
  `src/`. The handler adds no scraping behaviour of its own.
- **Never raises.** Fatal config/storage errors are converted to a structured
  result `{"ok": false, "status": "failed", "error_type": ..., "error_message": ...}`.
- **No secrets in output.** Known secret env values (`DATABASE_URL`,
  `BUFF_COOKIE`, Google creds, Discord webhook) are scrubbed from error messages
  before they leave the process. (A full redaction helper lands in the
  secrets-hardening phase.)
- **Writable paths.** When `AWS_LAMBDA_FUNCTION_NAME` is set, file-based defaults
  (`BUFF_SQLITE_PATH`, page-meta cache) are redirected to `/tmp`, the only
  writable location on Lambda. The Postgres backend writes no local files.

## Return shape

Success / partial / empty run:

```json
{
  "ok": true,
  "status": "partial_success",
  "started_at": "2026-06-03 00:00:00",
  "finished_at": "2026-06-03 00:00:18",
  "duration_seconds": 18.4,
  "attempted": 6,
  "succeeded": 4,
  "failed": 2,
  "skipped": 0,
  "error_count": 2
}
```

`ok` mirrors the cloud-safe exit policy: `true` for success/partial/empty,
`false` only when every attempted item failed or a fatal error occurred.

## Recommended Lambda env

```
STORAGE_BACKEND=postgres
DATABASE_URL=<from Secrets Manager>
BUFF_COOKIE=<from Secrets Manager>
BUFF_REQUEST_TIMEOUT=15
BUFF_MAX_RETRIES=3
BUFF_BACKOFF_BASE_SECONDS=1
BUFF_HIGH_VALUE_PAGES=<bounded, to stay under the 15-min limit>
```

## Local invocation (sanity check, no AWS)

```bash
python -c "import handler, json; print(json.dumps(handler.lambda_handler({}, None)))"
```

(This performs a real scrape using your local env/storage config. For a dry
run, point `STORAGE_BACKEND` at a disposable target.)

## Notes / limits

- The handler runs one scrape per invocation; bound the scope
  (`BUFF_HIGH_VALUE_PAGES`, `BUFF_MAX_GOODS_PER_RUN`) to fit the Lambda 15-min
  limit. If the desired scope cannot finish in time, use ECS Fargate (see
  `docs/aws-deploy-readiness.md`).
- Container packaging and CMD wiring are added in the Lambda-container phase.
