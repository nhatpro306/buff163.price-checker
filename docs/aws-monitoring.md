# AWS Monitoring & Observability

Make scheduled cloud runs easy to debug in CloudWatch.

## Structured run summary

Every run ends with a `ScrapeRunSummary` (`src/results.py`). Fields:

| Field | Meaning |
|-------|---------|
| `started_at` / `finished_at` | UTC timestamps |
| `duration_seconds` | wall-clock duration |
| `attempted` | items processed |
| `succeeded` | valid items stored |
| `failed` | items that errored |
| `skipped` / `invalid` | snapshots rejected by validation |
| `storage_backend` | `postgres` / `sqlite` / `sheets` |
| `status` | `success` / `partial_success` / `failed` |
| `error_count` | number of recorded errors |

- `summary.log_line()` — one-line human log (printed at end of every run):

  ```
  Scraper run finished: status=partial_success attempted=6 succeeded=4 failed=2 skipped=0 backend=postgres duration_seconds=18.4
  ```

- `summary.to_dict()` — structured dict, returned by the Lambda handler and
  ready for JSON logging. Contains **no secrets**.

## CloudWatch

- The handler's return value (the summary dict, or a `{"ok": false, ...}` error)
  is recorded by Lambda; search CloudWatch Logs for `Scraper run finished` to
  find the per-run one-liner.
- Error messages are passed through `redact_secrets` (see `docs/aws-secrets.md`)
  so DSNs, cookies, and webhooks never appear in logs.
- Error categories: validation skips (`skipped`/`invalid`), per-item failures
  (`failed` + `error_count`), and fatal errors (`{"ok": false, "error_type"}`).

### Suggested CloudWatch alarms

- Metric filter on `status=failed` → alarm (all items failed).
- Metric filter on `"ok": false` in handler output → alarm (fatal error).
- No-invocation alarm: alert if the schedule produced no logs in N hours.

## Health-check mode

Verify config and storage wiring **without scraping**:

```bash
# Lambda test event:
{ "mode": "health_check" }
# or set env BUFF_HEALTH_CHECK=1
```

Returns:

```json
{
  "ok": true,
  "status": "healthy",
  "mode": "health_check",
  "checks": {
    "storage_backend": "postgres",
    "database_url_present": true,
    "storage_init": "ok"
  }
}
```

`storage_init` runs the storage factory (connectivity/credentials probe). On
failure, `storage_error` is included **redacted**. Use this right after a deploy
or secret rotation to confirm the function is wired correctly before the next
scheduled scrape.
