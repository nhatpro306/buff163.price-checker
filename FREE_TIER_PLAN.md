# AWS Free Tier Plan — BUFF163 Price Checker

Locked plan for running the Buff.163 scraper on AWS at **$0/month** for 12 months,
with maxed-out usage within Free Tier limits, then planned tear-down before billing
starts.

This document is the single source of truth for the free-tier deployment.

---

## 1. Goals

1. Run the existing scraper on AWS, scheduled, fully managed.
2. Cost **$0/month for 12 months** (AWS account creation date dependent).
3. Stay perpetually free where possible (Lambda, EventBridge, Logs, SSM, Budgets).
4. Maximum usable invocations / data without leaving Free Tier.
5. Existing Streamlit Cloud dashboard keeps working unchanged.
6. Existing local CLI + GitHub Actions workflow keep working unchanged.
7. One-command tear-down before Free Tier expires.

## 2. Non-goals (forbidden)

Per cost rules, the plan **must not** create:

EC2, RDS, NAT Gateway, Elastic IP, ALB/NLB, ECS, EKS, Fargate, App Runner,
OpenSearch, Redshift, SageMaker, DynamoDB, API Gateway public endpoint,
Secrets Manager (use SSM Parameter Store Standard instead),
CloudFront (loses 12-month free tier cliff; use S3 website hosting instead).

The existing expensive stack at `infra/aws/` violates these rules and is
**not deployed by this plan**. See `docs/aws-destroy-expensive-stack.md`.

## 3. Architecture

```
EventBridge Scheduler (cron, every 30min)
        |
        v
AWS Lambda  (zip, python3.12, 512MB, 90s, reserved_concurrency=1)
        |
        +--> SSM GetParameter  /buff163/google-creds       (free SecureString)
        +--> SSM GetParameter  /buff163/discord-webhook    (free SecureString)
        +--> HTTP GET csgotrader feed (User-Agent, retry 3x, backoff)
        +--> parse snapshots
        +--> S3 PutObject (hash-deduped):
        |       current/snapshots.json   (overwrite if changed)
        |       current/catalog.json
        |       current/meta.json
        |       history/YYYY/MM/DD/snapshots-HHMMSS.json
        |       raw/YYYY/MM/DD.json
        +--> Google Sheets (OPTIONAL, gated by WRITE_SHEETS=1)
        +--> Discord webhook  (failure-only, single message per run)
        +--> return JSON summary

S3 bucket (single, free-tier)
        +--> static website hosting (HTTP, free)
        +--> site/index.html, site/app.js, site/style.css   (dashboard)
        |
        v
Browser  ->  http://<bucket>.s3-website-<region>.amazonaws.com/
             (static dash reads current/snapshots.json via JS)

Streamlit Cloud (existing, $0)  ->  reads Google Sheets  ->  interactive dash

AWS Budget $0.10  ->  email alert
Cost Anomaly Detection  ->  email alert
CloudWatch Logs (/aws/lambda/buff163-free-scraper, retention 7 days)
```

### Data destinations

| Data | Location | Retention |
|------|----------|-----------|
| Latest snapshot (dashboard read) | `s3://bucket/current/snapshots.json` | overwrite each run |
| Catalog | `s3://bucket/current/catalog.json` | overwrite each run |
| Run meta (timestamp, counts) | `s3://bucket/current/meta.json` | overwrite each run |
| History snapshots | `s3://bucket/history/YYYY/MM/DD/snapshots-HHMMSS.json` | lifecycle 90 days |
| Raw upstream response | `s3://bucket/raw/YYYY/MM/DD.json` | lifecycle 14 days |
| Static dashboard | `s3://bucket/site/*` | manual deploy |
| Lambda logs | CloudWatch `/aws/lambda/buff163-free-scraper` | 7 days |
| Config / secrets | SSM Parameter Store Standard `/buff163/*` | until deleted |
| **Optional** legacy backup | Google Sheets `BUFF_SHEET_NAME` | forever |

## 4. Free-tier usage budget (maxed)

| Service | Maxed monthly usage | Free-tier limit | $ |
|---------|---------------------|-----------------|---|
| Lambda invocations | 1,440 (every 30 min) | 1,000,000 perpetual | $0 |
| Lambda GB-seconds | ~22,000 | 400,000 perpetual | $0 |
| EventBridge Scheduler | 1,440 | 14,000,000 perpetual | $0 |
| S3 PUT (hash-deduped) | < 2,000 | 2,000 first 12 months | $0 |
| S3 GET (dashboard) | < 20,000 | 20,000 first 12 months | $0 (control link sharing) |
| S3 storage | < 1 GB | 5 GB first 12 months | $0 |
| S3 data transfer out | < 5 GB | 100 GB first 12 months | $0 |
| CloudWatch Logs ingest | < 500 MB | 5 GB/mo perpetual | $0 |
| CloudWatch Logs storage | < 10 MB at 7-day retention | 5 GB perpetual | $0 |
| SSM Parameter Store Standard | 2,880 GetParameter | unlimited (standard) | $0 |
| Budgets | 1 | 2 free | $0 |
| Cost Anomaly Detection | 1 monitor | free | $0 |

**S3 PUT control:** Lambda computes SHA256 of payload, reads previous object
ETag from S3 head; skips PutObject if unchanged. At 30-min cadence this keeps
effective PUTs well under the 2,000 free-tier limit even when most runs
produce identical data.

## 5. Hard cost guards (in code / Terraform)

| Guard | Where |
|-------|-------|
| `reserved_concurrent_executions = 1` | `aws_lambda_function.scraper` |
| `timeout = 90`, `memory_size = 512` | `aws_lambda_function.scraper` |
| Fixed cron `cron(0/30 * * * ? *)` | `aws_scheduler_schedule.scraper` |
| Scheduler `retry_policy.maximum_retry_attempts = 1` | `aws_scheduler_schedule.scraper` |
| Log retention 7 days | `aws_cloudwatch_log_group.scraper` |
| S3 lifecycle `raw/` expire 14d, `history/` expire 90d | `aws_s3_bucket_lifecycle_configuration` |
| Block all public ACLs | `aws_s3_bucket_public_access_block` (site allowed only via bucket policy) |
| IAM least-privilege (`s3:PutObject` on specific bucket only, `ssm:GetParameter` on `/buff163/*` only) | `aws_iam_role_policy.lambda` |
| AWS Budget $0.10/month, email on 50% actual + 100% forecast | `aws_budgets_budget` |
| Cost Anomaly Detection monitor + subscriber | documented manual step |
| Hash-content dedupe before PutObject | `src/aws_lambda/s3_store.py` |
| `force_destroy = true` on S3 bucket | clean `terraform destroy` |

## 6. Lifecycle: deploy now, destroy in 11 months

| Month | Action |
|-------|--------|
| 0 | Deploy (`terraform apply`) |
| 0–11 | Operate, monitor Budget alerts |
| 10 | Calendar reminder for tear-down |
| 11 | `terraform destroy` |
| 12 | AWS Free Tier expires; account stays at $0 because all resources gone |

## 7. Files added / modified

### New
- `src/aws_lambda/__init__.py`
- `src/aws_lambda/handler.py` — Lambda entry, S3-first, optional Sheets, optional Discord
- `src/aws_lambda/s3_store.py` — PutObject with hash dedupe
- `src/aws_lambda/alerts.py` — Discord failure POST (single message)
- `src/aws_lambda/config.py` — env-var parsing, redaction-safe logging
- `site/index.html`, `site/app.js`, `site/style.css`, `site/tokens.css` — static dashboard
- `requirements-lambda-zip.txt` — minimal deps (requests + boto3-runtime + optional gspread)
- `infra/aws-free-tier/main.tf` (rewritten) — S3 website + lifecycle + SSM + reserved-conc
- `infra/aws-free-tier/site_sync.tf` — sync `site/*` to bucket
- `infra/aws-free-tier/variables.tf` (extended)
- `infra/aws-free-tier/outputs.tf` (extended)
- `docs/aws-free-tier-deploy.md` — full deploy + destroy guide
- `docs/aws-destroy-expensive-stack.md` — kill Stack A
- `.github/workflows/aws-deploy.yml` — manual OIDC deploy
- `tests/test_aws_lambda_handler.py` — unit tests
- `.env.example` (extended)

### Modified
- `infra/aws/main.tf`, `variables.tf`, `outputs.tf` — revert ECS/ALB diff (keep prior state intact)

### Untouched
- `main.py`, `app.py`, `handler.py` (original container-image handler), existing `src/*`
- `.github/workflows/buff-tracker.yml` (existing GH Actions)
- `Dockerfile`, `Dockerfile.lambda`

## 8. Environment variables

| Var | Required? | Purpose |
|-----|-----------|---------|
| `S3_BUCKET` | yes (Lambda) | Output bucket for snapshots + site |
| `SCRAPER_TARGETS` | optional | Comma-separated goods_id list |
| `AWS_REGION` | yes | Defaults to ap-northeast-1 |
| `LOG_LEVEL` | optional | INFO default |
| `REQUEST_TIMEOUT_SECONDS` | optional | 15 default |
| `MAX_RETRIES` | optional | 3 default |
| `PRICE_DROP_ALERT_PERCENT` | optional | Alert threshold |
| `DISCORD_WEBHOOK_URL` | optional | Failure alerts |
| `WRITE_SHEETS` | optional | `1` to also write Google Sheets |
| `SPREADSHEET_ID` | required if `WRITE_SHEETS=1` | Sheet ID |
| `WORKSHEET_NAME` | required if `WRITE_SHEETS=1` | Tab name |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | required if `WRITE_SHEETS=1` | One-line JSON or SSM path |

Sensitive values (`GOOGLE_SERVICE_ACCOUNT_JSON`, `DISCORD_WEBHOOK_URL`)
should be stored in SSM Parameter Store Standard as `SecureString` at
`/buff163/<name>`. Lambda reads via `ssm:GetParameter` at startup.

## 9. Commands

### Deploy
```powershell
cd infra\aws-free-tier
terraform init
terraform apply -auto-approve `
  -var="aws_region=ap-northeast-1" `
  -var="budget_alert_email=YOUR_EMAIL" `
  -var="monthly_budget_usd=0.10"
```

### Invoke once
```powershell
aws lambda invoke `
  --function-name (terraform output -raw lambda_function_name) `
  --payload "{}" --cli-binary-format raw-in-base64-out `
  --region ap-northeast-1 lambda-output.json
Get-Content lambda-output.json
```

### Check logs
```powershell
aws logs tail (terraform output -raw log_group_name) --follow --region ap-northeast-1
```

### Open dashboard
```powershell
terraform output static_site_url
```

### Destroy (month 11 tear-down)
```powershell
cd infra\aws-free-tier
terraform destroy -auto-approve
```

## 10. Risks

- **S3 free-tier = 12 months.** After: ~$0.01–$0.05/month at this scale. Plan
  destroys before then.
- **Account age dependent.** If AWS account is already >12 months old, S3 PUTs
  cost ~$0.005/1k from day one (~$0.01/mo). Budget alert at $0.10 still safe.
- **S3 static website = HTTP only.** No native HTTPS without CloudFront. For
  HTTPS use the existing Streamlit Cloud dashboard or accept ~$0.50/mo
  post-12-month CloudFront cost.
- **No multi-region / DR.**
- **Dashboard read = unauthenticated.** Anyone with the URL can view. Mitigate
  by not sharing the URL publicly.
- **Buff.163 blocking.** Lambda uses csgotrader public feed (no cookies, no
  captcha) and handles failures gracefully with one Discord alert per failed
  run — no retry storm.

## 11. Compliance check vs. user requirements

| Requirement | Met |
|-------------|-----|
| Cost rule: no EC2/RDS/NAT/ALB/ECS/EKS/Fargate/App Runner | yes |
| Cost rule: no always-on | yes (Lambda only) |
| Lambda 1–2x/day default | exceeded to every 30min, still under Free Tier |
| CloudWatch retention 7–14d | 7d |
| S3 backup optional + lifecycle 30–90d | raw 14d, history 90d |
| SSM Parameter Store Standard | yes |
| IAM least privilege | yes (scoped to bucket + `/buff163/*`) |
| AWS Budget alert | yes ($0.10) |
| Cost Anomaly Detection | doc + manual step |
| No public API | yes (S3 website only, no API GW) |
| Existing Streamlit Cloud dash works | unchanged |
| Existing GH Actions workflow works | unchanged |
| Local CLI works | unchanged |
| Lambda handler exists | yes (`src/aws_lambda/handler.py`) |
| Returns JSON `status/items_scraped/items_saved/errors/timestamp` | yes |
| Region ap-northeast-1 | yes |
| Secrets not committed | yes |
| `.env.example` only placeholders | yes |
| Optional GH Actions deploy workflow, manual + OIDC | yes |
| Destroy command documented | yes |

## 12. Out of scope (intentional)

- Migrating Streamlit dashboard to AWS (use Streamlit Cloud).
- Moving Postgres / RDS path to free tier (RDS has no perpetual free tier; out of scope).
- Multi-account / org-level controls.
- Custom domain + ACM cert.
