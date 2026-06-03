# AWS Deployment Checklist

Single-page checklist for deploying the BUFF163 scraper to AWS. Fill the
**values** column from your account. **Never commit real secret values, database
URLs, cookies, or AWS keys.** See `aws-production-runbook.md` for full steps and
`aws-secrets.md` for secret handling.

## Prerequisites

- [ ] **Docker Desktop running** (daemon up) — required to build the image.
- [ ] **Terraform installed** (`>= 1.5`) — `choco install terraform` or
      `winget install Hashicorp.Terraform`; verify `terraform version`.
- [ ] **AWS CLI v2** configured (`aws sts get-caller-identity` works).
- [ ] Reachable PostgreSQL database.
- [ ] Valid BUFF163 session cookie.

## Configuration values

| Setting | Terraform var | Default | Your value |
|---------|---------------|---------|-----------|
| AWS region | `aws_region` | `ap-southeast-1` | |
| ECR repo name | `ecr_repo_name` | `buff163-scraper` | |
| Lambda function name | `lambda_function_name` | `buff163-scraper` | |
| Lambda memory (MB) | `lambda_memory_mb` | `1024` | |
| Lambda timeout (s) | `lambda_timeout_seconds` | `900` | |
| Schedule expression | `schedule_expression` | `rate(12 hours)` | |
| Schedule enabled | `schedule_enabled` | `true` (set **false** first) | |
| Log retention (days) | `log_retention_days` | `30` | |
| Image tag | `image_tag` | `latest` (use git SHA) | |

## Secret names (Secrets Manager — names only, never values)

| Secret | Suggested name | Terraform var (ARN) |
|--------|----------------|---------------------|
| Postgres DSN | `buff163/DATABASE_URL` | `database_url_secret_arn` |
| BUFF163 cookie | `buff163/BUFF_COOKIE` | `buff_cookie_secret_arn` |
| (all readable ARNs) | — | `secret_arns` |

PostgreSQL secret **format** (value stored in Secrets Manager, never committed):

```
postgresql://USER:PASSWORD@HOST:5432/DBNAME
```

## Required env vars (Lambda)

| Var | Value | Source |
|-----|-------|--------|
| `STORAGE_BACKEND` | `postgres` | `extra_env` |
| `DATABASE_URL` | — | resolved from `DATABASE_URL_SECRET_ARN` at runtime |
| `BUFF_COOKIE` | — | resolved from `BUFF_COOKIE_SECRET_ARN` at runtime |
| `BUFF_REQUEST_TIMEOUT` | `15` | `extra_env` |
| `BUFF_MAX_RETRIES` | `3` | `extra_env` |
| `BUFF_BACKOFF_BASE_SECONDS` | `1` | `extra_env` |
| `BUFF_HIGH_VALUE_PAGES` | low (bound runtime) | `extra_env` |
| `BUFF_MAX_GOODS_PER_RUN` | low (bound runtime) | `extra_env` |

## Build & push

```bash
# Build (amd64)
docker build --platform linux/amd64 -f Dockerfile.lambda -t buff163-scraper:$(git rev-parse --short HEAD) .

# Push to ECR
AWS_REGION=ap-southeast-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO=buff163-scraper
TAG=$(git rev-parse --short HEAD)
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
docker tag buff163-scraper:$TAG "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:$TAG"
docker push "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:$TAG"
```

## Terraform

```bash
cd infra/aws
cp terraform.tfvars.example terraform.tfvars   # edit; NEVER commit real values
terraform fmt -check
terraform init -backend=false   # validation only
terraform validate
# With AWS creds + tfvars (ARNs, not values):
terraform plan -var="image_tag=$TAG"
# Deploy (after review):
terraform apply -var="image_tag=$TAG"
```

> Do **not** run `terraform apply` until Docker build + `terraform validate`
> pass and review is complete.

## Verify

```bash
FN=$(terraform output -raw lambda_function_name)

# Health check (no scrape):
aws lambda invoke --function-name "$FN" \
  --payload '{"mode":"health_check"}' --cli-binary-format raw-in-base64-out /tmp/hc.json
cat /tmp/hc.json   # expect {"ok": true, "status": "healthy", ...}

# Manual scraper run:
aws lambda invoke --function-name "$FN" --payload '{}' \
  --cli-binary-format raw-in-base64-out /tmp/run.json
cat /tmp/run.json  # expect run summary {"ok": true, "status": "...", ...}
```

CloudWatch log group: **`/aws/lambda/buff163-scraper`**

```bash
aws logs tail "$(terraform output -raw log_group_name)" --follow
# Look for: "Scraper run finished: status=... backend=postgres ..."
```

PostgreSQL verification:

```sql
SELECT ts, goods_id, price, listings FROM snapshots ORDER BY ts DESC LIMIT 20;
```

## Rollback / cleanup

```bash
# Revert to previous image:
terraform apply -var="image_tag=<previous-good-tag>"

# Pause schedule (no destroy):
terraform apply -var="schedule_enabled=false"
```

> **DESTROY WARNING:** `terraform destroy` removes the ECR repo (+ images),
> Lambda, IAM roles, log group, and schedule. It does **not** touch your
> PostgreSQL data, but it is irreversible for the AWS infra. Use only for full
> teardown.

## Safety reminders

- [ ] No real secret values committed (`.env`, tfvars, creds are git-ignored).
- [ ] IAM grants `GetSecretValue` on listed ARNs only (no `*`).
- [ ] Schedule starts **disabled / conservative**; enable only after a clean
      manual run.
- [ ] `BUFF_HIGH_VALUE_PAGES` / `BUFF_MAX_GOODS_PER_RUN` bounded to stay under
      the Lambda 15-minute limit (else ECS Fargate fallback).
