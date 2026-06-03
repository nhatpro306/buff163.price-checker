# AWS Production Deployment Runbook

End-to-end instructions to deploy and operate the BUFF163 scraper on AWS as a
scheduled Lambda job. Companion docs: `aws-deploy-readiness.md`, `aws-lambda.md`,
`aws-container-deploy.md`, `aws-infra.md`, `aws-secrets.md`, `aws-monitoring.md`.

## 1. Prerequisites

- AWS account + IAM user/role with admin (or scoped deploy) permissions.
- Local tools: `aws` CLI v2 (configured), `docker`, `terraform >= 1.5`, `git`.
- A reachable PostgreSQL database (the storage backend on `main`).
- A valid BUFF163 session cookie.

## 2. Required AWS services

ECR (image), Lambda (container), EventBridge Scheduler (schedule),
Secrets Manager (secrets), CloudWatch Logs (logs), IAM (roles).

## 3. Required secrets

Create in Secrets Manager (values never committed, never in Terraform state):

```bash
aws secretsmanager create-secret --name buff163/DATABASE_URL \
  --secret-string "postgresql://USER:PASS@HOST:5432/DB"
aws secretsmanager create-secret --name buff163/BUFF_COOKIE \
  --secret-string "session=...; csrf_token=..."
# Note the returned ARNs.
```

GitHub Actions (if building in CI later): store AWS creds as repo secrets;
never print them.

## 4. Build the container

```bash
docker build --platform linux/amd64 -f Dockerfile.lambda -t buff163-scraper:$(git rev-parse --short HEAD) .
```

## 5. Push to ECR

```bash
AWS_REGION=ap-southeast-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO=buff163-scraper
TAG=$(git rev-parse --short HEAD)

# Create repo first time (or let Terraform create it — see step 6):
aws ecr describe-repositories --repository-names "$REPO" --region "$AWS_REGION" \
  || aws ecr create-repository --repository-name "$REPO" --region "$AWS_REGION"

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

docker tag buff163-scraper:$TAG "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:$TAG"
docker push "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:$TAG"
```

## 6. Deploy Lambda + schedule (Terraform)

```bash
cd infra/aws
cp terraform.tfvars.example terraform.tfvars   # then edit
terraform init

# First run: create ECR (if not done in step 5), push image, then full apply.
terraform apply -target=aws_ecr_repository.scraper   # optional if repo exists
terraform apply -var="image_tag=$TAG" \
  -var='database_url_secret_arn=arn:aws:secretsmanager:...:buff163/DATABASE_URL-xxxx' \
  -var='buff_cookie_secret_arn=arn:aws:secretsmanager:...:buff163/BUFF_COOKIE-xxxx' \
  -var='secret_arns=["arn:...DATABASE_URL-xxxx","arn:...BUFF_COOKIE-xxxx"]'
```

`extra_env` defaults set `STORAGE_BACKEND=postgres` and the timeout/retry knobs.
Bound the run scope (`BUFF_HIGH_VALUE_PAGES`, `BUFF_MAX_GOODS_PER_RUN`) via
`extra_env` to stay under the 15-minute Lambda limit.

## 7. Configure Secrets Manager (recap)

Secrets created in step 3; their ARNs are passed to Terraform in step 6. IAM
grants the Lambda `GetSecretValue` on **only** those ARNs. The handler resolves
`DATABASE_URL`/`BUFF_COOKIE` from the ARNs at runtime.

## 8. Configure EventBridge Scheduler

Set by Terraform (`schedule_expression`, default `rate(12 hours)`). Change:

```bash
terraform apply -var='schedule_expression=cron(0 0,12 * * ? *)'
```

## 9. Manual test

```bash
FN=$(terraform output -raw lambda_function_name)

# Health check (no scrape):
aws lambda invoke --function-name "$FN" \
  --payload '{"mode":"health_check"}' --cli-binary-format raw-in-base64-out /tmp/hc.json
cat /tmp/hc.json   # expect {"ok": true, "status": "healthy", ...}

# Real run:
aws lambda invoke --function-name "$FN" --payload '{}' \
  --cli-binary-format raw-in-base64-out /tmp/run.json
cat /tmp/run.json  # expect run summary {"ok": true, "status": "...", ...}
```

## 10. Check CloudWatch Logs

```bash
aws logs tail "$(terraform output -raw log_group_name)" --follow
# Find the one-liner: "Scraper run finished: status=... backend=postgres ..."
```

## 11. Verify data in PostgreSQL

```sql
SELECT ts, goods_id, price, listings
FROM snapshots
ORDER BY ts DESC
LIMIT 20;
```

Confirm fresh rows at the schedule cadence and no duplicate `(ts, goods_id)`.

## 12. Update deployment

```bash
# Build + push a new tag (steps 4-5), then:
terraform apply -var="image_tag=<new-tag>"
# or fast path:
aws lambda update-function-code --function-name "$FN" --image-uri "<ecr-url>:<new-tag>"
```

## 13. Rollback

```bash
terraform apply -var="image_tag=<previous-good-tag>"   # revert image
terraform apply -var="schedule_enabled=false"          # pause schedule
# Last resort full teardown:
terraform destroy
```

## 14. Cost / risk notes

- Lambda: pay-per-invocation; a 12-hourly bounded run is well within free/low
  tier. Memory 1024 MB × seconds billed.
- ECR: storage for image(s) (~hundreds of MB). Prune old tags.
- Secrets Manager: per-secret monthly cost + per-API-call.
- CloudWatch Logs: retention set to 30 days (`log_retention_days`).
- Risk: BUFF163 cookie expiry → 403s; rotate `BUFF_COOKIE`. Unbounded scope can
  exceed 15-min Lambda limit → use ECS Fargate fallback (`aws-deploy-readiness.md`).

## 15. Common errors & fixes

| Symptom (CloudWatch) | Likely cause | Fix |
|----------------------|--------------|-----|
| `{"ok": false, "error_type": "OperationalError"}` | bad/missing `DATABASE_URL` | check secret value + IAM `GetSecretValue`; run health check |
| Many `skipped`/`invalid` | BUFF returning empty/odd data | check `BUFF_COOKIE` validity (403 → fail fast) |
| `status=failed` (all items) | network/auth or storage down | health-check mode; verify DB reachability |
| `Task timed out after 900.00 seconds` | scope too large for Lambda | lower `BUFF_HIGH_VALUE_PAGES`/`BUFF_MAX_GOODS_PER_RUN`, or move to ECS Fargate |
| `Read-only file system` | sqlite/local write on Lambda | use `STORAGE_BACKEND=postgres`; `/tmp` is the only writable path |
| Image pull / arch error | image built for arm64 | rebuild `--platform linux/amd64` |
