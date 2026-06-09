# AWS Free Tier Deployment Guide

End-to-end guide for deploying the BUFF163 price-checker scraper on AWS
within the Free Tier. Target: **$0/month for 12 months**, then planned
tear-down before any service leaves the Free Tier window.

This guide covers the stack in `infra/aws-free-tier/`. The separate
`infra/aws/` stack (RDS + ECS/App Runner) is **not used** and should be
destroyed if previously applied — see `aws-destroy-expensive-stack.md`.

---

## 1. Architecture

```
EventBridge Scheduler (cron, default 1x/day, can go to every 30 min)
        |
        v
AWS Lambda (zip, python3.11, 256 MB, 120 s, reserved_concurrency=1)
   entry: static_site_handler.lambda_handler
        |
        +--> HTTP GET csgotrader public feed (urllib, retry+backoff)
        +--> SSM GetParameter /buff163/google-creds      (optional)
        +--> SSM GetParameter /buff163/discord-webhook   (optional)
        +--> S3 PutObject (hash-deduped via x-amz-meta-sha):
        |       data.json + index.html                (static dashboard)
        |       current/snapshots.json                  (latest)
        |       current/meta.json                        (run metadata)
        |       history/YYYY/MM/DD/snapshots-HHMMSS.json (lifecycle 90d)
        |       raw/YYYY/MM/DD.json                      (lifecycle 14d)
        +--> Google Sheets append_rows                   (only if WRITE_SHEETS=1)
        +--> Discord webhook POST                        (only on failure)
        +--> return JSON summary

S3 (private bucket) <--- CloudFront (PriceClass_100) ---> Browser (HTTPS)
                                                          dashboard URL
```

Region default: **ap-northeast-1 (Tokyo)**. Switchable via `aws_region` var.

## 2. Cost Safety Explanation

| Service | Free Tier limit | Maxed usage at 30-min schedule | $ |
|---------|-----------------|--------------------------------|---|
| Lambda invocations | 1,000,000/mo perpetual | 1,440 | $0 |
| Lambda GB-s | 400,000/mo perpetual | ~22,000 | $0 |
| EventBridge Scheduler | 14M invocations/mo perpetual | 1,440 | $0 |
| S3 PUT | 2,000/mo first 12 months | < 2,000 (hash-deduped) | $0 |
| S3 GET | 20,000/mo first 12 months | dashboard reads | $0 if < 650/day |
| S3 storage | 5 GB first 12 months | < 1 GB | $0 |
| S3 data out | 100 GB first 12 months | tiny | $0 |
| CloudFront data out | 1 TB first 12 months | tiny | $0 |
| CloudWatch Logs | 5 GB/mo perpetual | < 500 MB | $0 |
| SSM Parameter Store Standard | unlimited free | 2 reads/run | $0 |
| Budgets | 2 free | 1 | $0 |

Hash-dedupe is implemented in `src/aws_lambda/s3_store.py`: each PUT first
HEADs the object and compares the SHA-256 of the new body against the stored
`x-amz-meta-sha`. Identical content => no PUT.

## 3. AWS Account Preparation

1. Create AWS account (or use existing) — note the **account creation date**;
   this drives when the 12-month S3 / CloudFront free tier expires.
2. In the root account, enable **MFA**.
3. Create an IAM user for deployment (do **not** deploy as root). Attach
   `AdministratorAccess` for first deploy; tighten later. Generate access keys.
4. Enable **AWS Billing access for IAM users** in account settings.
5. Enable **Cost Explorer** in the Billing console (free, takes ~24 h).
6. Enable **Free Tier usage alerts** in account preferences.

## 4. AWS CLI Setup

Install AWS CLI v2 and Terraform v1.5+. Then:

```powershell
aws configure
# AWS Access Key ID     [None]: ...
# AWS Secret Access Key [None]: ...
# Default region name   [None]: ap-northeast-1
# Default output format [None]: json

aws sts get-caller-identity
```

Confirm the Account / UserId belongs to you.

## 5. AWS Budget Setup

Create a $0.10 budget (the lowest meaningful threshold) with email alerts so
you hear about any spend immediately:

```powershell
aws budgets create-budget `
  --account-id (aws sts get-caller-identity --query Account --output text) `
  --budget '{
      "BudgetName": "buff163-free-tier",
      "BudgetLimit": {"Amount": "0.10", "Unit": "USD"},
      "TimeUnit": "MONTHLY",
      "BudgetType": "COST"
    }' `
  --notifications-with-subscribers '[
      {
        "Notification": {
          "NotificationType": "ACTUAL",
          "ComparisonOperator": "GREATER_THAN",
          "Threshold": 1,
          "ThresholdType": "ABSOLUTE_VALUE"
        },
        "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "YOU@example.com"}]
      }
    ]'
```

The Terraform stack also creates a managed budget when `budget_alert_email`
is set. Pick one mechanism, not both.

### Cost Anomaly Detection

```powershell
aws ce create-anomaly-monitor --anomaly-monitor `
  '{"MonitorName":"buff163-anomaly","MonitorType":"DIMENSIONAL","MonitorDimension":"SERVICE"}'
```

Then attach an anomaly subscription with your email (one-time, via console is
fine).

## 6. Environment / SSM Setup

Sensitive values live in SSM Parameter Store Standard (free, perpetual). The
Lambda reads them at run time via `ssm:GetParameter` scoped to `/buff163/*`.

Create the parameters (only those you need):

```powershell
# (Optional) Discord webhook URL for failure alerts.
aws ssm put-parameter `
  --name "/buff163/discord-webhook" `
  --type "SecureString" `
  --value "https://discord.com/api/webhooks/.../..." `
  --region ap-northeast-1

# (Optional) Google service-account JSON, one line, only if WRITE_SHEETS=1.
aws ssm put-parameter `
  --name "/buff163/google-creds" `
  --type "SecureString" `
  --value (Get-Content path\to\service-account.json -Raw) `
  --region ap-northeast-1
```

Non-sensitive config (bucket, schedule, retention, etc.) lives in Terraform
variables — see `infra/aws-free-tier/variables.tf`.

## 7. Package the Lambda

For the **base** path (S3 only), no `pip install` step is needed; the zip is
built by Terraform from `static_site_handler.py` + the `src/aws_lambda/` helpers
and uses only the stdlib + the runtime-provided `boto3`.

For the **Sheets** path (`WRITE_SHEETS=1`), bundle the optional deps:

```powershell
cd infra\aws-free-tier
pip install -r ..\..\requirements-lambda-zip.txt -t .\build\deps
```

Then either add `${path.module}/build/deps` as a second `source_dir` block in
`main.tf` (advanced) or use the simpler approach: deploy without Sheets first,
then enable it later.

## 8. Deploy

```powershell
cd infra\aws-free-tier
terraform init
terraform plan -out plan.tfplan `
  -var="aws_region=ap-northeast-1" `
  -var="budget_alert_email=YOU@example.com" `
  -var="monthly_budget_usd=0.10"
terraform apply plan.tfplan
```

To enable optional Sheets writing later:

```powershell
terraform apply `
  -var="aws_region=ap-northeast-1" `
  -var="write_sheets=true" `
  -var="spreadsheet_id=1AbCdEf..." `
  -var="worksheet_name=History"
```

To enable Discord alerts:

```powershell
terraform apply `
  -var="aws_region=ap-northeast-1" `
  -var="discord_webhook_ssm_param=/buff163/discord-webhook"
```

## 9. Test the Lambda

```powershell
$fn = terraform output -raw lambda_function_name
aws lambda invoke `
  --function-name $fn `
  --payload "{}" `
  --cli-binary-format raw-in-base64-out `
  --region ap-northeast-1 `
  lambda-output.json
Get-Content lambda-output.json
```

Expected response shape (truncated):
```json
{
  "status": "success",
  "ok": true,
  "items_scraped": 320,
  "items_saved": 320,
  "items_saved_sheets": 0,
  "errors": [],
  "timestamp": "2026-xx-xxTxx:xx:xxZ",
  "bucket": "...",
  "duration_seconds": 4.3
}
```

Health-check mode (no scrape, no S3 writes):

```powershell
aws lambda invoke --function-name $fn `
  --payload '{"mode":"health_check"}' `
  --cli-binary-format raw-in-base64-out `
  --region ap-northeast-1 ` health.json
Get-Content health.json
```

## 10. Verify Google Sheets Updated (only if WRITE_SHEETS=1)

Open the spreadsheet you configured. The targeted worksheet should contain
new rows appended at the bottom with the run timestamp.

If the response includes `"sheets_skipped_missing_creds_in_ssm"` in `errors`,
confirm the `/buff163/google-creds` SSM parameter exists and that the service
account email has Editor access on the spreadsheet.

## 11. Check CloudWatch Logs

```powershell
$lg = terraform output -raw log_group_name
aws logs tail $lg --follow --region ap-northeast-1
```

Useful log markers:
- `s3_put` — wrote an object
- `s3_skip_unchanged` — dedupe avoided a PUT
- `sheets_write_failed:` / `scrape_failed:` — error path
- `discord_alert_sent` / `discord_alert_failed` — alert path

## 12. Open the Dashboard

```powershell
terraform output cloudfront_url
```

The first deployment takes ~5–10 minutes for CloudFront to fully propagate.

## 13. Disable the Schedule (pause without destroying)

```powershell
$sched = terraform output -raw schedule_name
aws scheduler update-schedule `
  --name $sched `
  --schedule-expression (terraform output -raw current_schedule_expression) `
  --state DISABLED `
  --region ap-northeast-1
```

Re-enable with `--state ENABLED`.

## 14. Destroy Everything

When the 12-month free tier window approaches end, or when you no longer
want the deployment:

```powershell
cd infra\aws-free-tier
terraform destroy
```

This removes:
- Lambda function + role
- EventBridge schedule + role
- S3 bucket (`force_destroy = true` requires applying a small change in
  `main.tf` first if you want Terraform to delete a non-empty bucket; by
  default you must empty the bucket manually before destroy)
- CloudFront distribution (takes ~15 min to disable + delete)
- CloudWatch log group
- IAM policy attachments
- Budget (if created)

SSM parameters under `/buff163/*` are **not** managed by Terraform and must be
deleted manually:

```powershell
aws ssm delete-parameter --name "/buff163/discord-webhook" --region ap-northeast-1
aws ssm delete-parameter --name "/buff163/google-creds"    --region ap-northeast-1
```

If S3 still contains objects after `terraform destroy` fails:

```powershell
$bucket = terraform output -raw bucket_name
aws s3 rm s3://$bucket --recursive
aws s3 rb s3://$bucket
```

## 15. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Lambda response `errors:["scrape_failed: HTTPError"]` | Upstream csgotrader feed down or rate-limited | Retry once; check `aws logs tail`; do not increase schedule frequency |
| `errors:["s3_write_failed: AccessDenied"]` | IAM policy missing or bucket name mismatch | Re-apply Terraform; confirm bucket exists |
| `errors:["sheets_skipped_missing_creds_in_ssm"]` | SSM parameter missing or no decrypt permission | Create the parameter (section 6); ensure path matches `GOOGLE_CREDS_SSM_PARAM` |
| Empty CloudFront page | First propagation pending | Wait 10 min after first deploy |
| Sudden cost spike | Check Cost Explorer per service | Run destroy guide for Stack A; verify no orphan EC2/RDS/NAT |
| `terraform destroy` fails on S3 bucket | Bucket non-empty | `aws s3 rm s3://... --recursive` then retry |

## 16. Security Checklist

- [ ] No secrets in `.env`, Terraform `*.tfvars`, or committed files
- [ ] SSM parameters use `SecureString` type
- [ ] IAM policy on the Lambda role scoped to the bucket + `/buff163/*` only
- [ ] CloudFront origin uses Origin Access Control; bucket blocks public access
- [ ] Lambda env vars contain no secret values (only SSM parameter names)
- [ ] Discord webhook URL never appears in logs
- [ ] Service-account JSON never appears in logs
- [ ] No `s3:*` or `ssm:*` wildcard actions
- [ ] No `*` Resource on any IAM statement
- [ ] Buff.163 cookies / login not used (csgotrader public feed only)

## 17. Cost Checklist

Before deploy:
- [ ] AWS account creation date is recorded; free-tier expiry calendared
- [ ] Budget alert created at $0.10
- [ ] Cost Anomaly Detection enabled with email subscription
- [ ] Region confirmed (`ap-northeast-1` recommended)
- [ ] No EC2 / RDS / NAT / ALB / Fargate / App Runner in account
- [ ] Lambda schedule no more frequent than every 30 min
- [ ] CloudWatch retention set (7 days)
- [ ] S3 lifecycle rules applied (raw 14d, history 90d)

After deploy:
- [ ] First Lambda invoke returns `status: "success"`
- [ ] CloudWatch logs visible
- [ ] Dashboard renders at CloudFront URL
- [ ] AWS Billing console shows $0 estimated charges 24 h after deploy
- [ ] No unexpected resources in EC2 / RDS / ELB consoles
