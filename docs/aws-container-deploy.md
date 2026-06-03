# AWS Lambda Container Deployment

Package the scraper as a Lambda container image and push it to Amazon ECR.

## Files

- `Dockerfile.lambda` — Lambda Python 3.11 base image; `CMD ["handler.lambda_handler"]`.
- `requirements-lambda.txt` — minimal runtime deps (no dev tooling, no
  dashboard-only libs).
- `.dockerignore` — keeps secrets, `.env*`, credentials, `*.bak`, local DBs,
  tests, docs, and dashboard config out of the image.

The Streamlit dashboard image remains the separate top-level `Dockerfile`.

## What is (not) in the image

Included: `handler.py`, `main.py`, `market_*.py`, top-level scraper modules in
`src/`, `src/db/`, and `src/storage/`.
Excluded: `.env*`, credentials/service-account JSON, local DB files (`*.db`,
`*.sqlite`, `*.sqlite3`), `tests/`, `docs/`, `app.py`, `src/dashboard/`, and
`.git/`. No secrets are baked in — they come from Secrets Manager at runtime.

## Local build

```bash
# From repo root
docker build -f Dockerfile.lambda -t buff163-scraper:local .
```

## Local smoke test (Lambda Runtime Interface Emulator)

The AWS base image ships the Runtime Interface Emulator, so you can invoke the
handler locally without deploying:

```bash
# Run the container (pass env via --env-file of a LOCAL, untracked .env)
docker run --rm -p 9000:8080 \
  -e STORAGE_BACKEND=postgres \
  -e DATABASE_URL="$DATABASE_URL" \
  buff163-scraper:local

# In another shell, invoke:
curl -s "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{}'
# Expect a JSON run summary: {"ok": true, "status": "...", ...}
```

> Use a disposable/local Postgres for smoke testing. Never put real secrets on
> the command line in shared shells; prefer `--env-file ./.env` where `.env` is
> git-ignored.

## Push to ECR

```bash
AWS_REGION=ap-southeast-1
ACCOUNT_ID=<your-account-id>
REPO=buff163-scraper

aws ecr describe-repositories --repository-names "$REPO" --region "$AWS_REGION" \
  || aws ecr create-repository --repository-name "$REPO" --region "$AWS_REGION"

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

docker tag buff163-scraper:local "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest"
docker push "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO:latest"
```

Lambda function creation / scheduling is handled by the infrastructure phase
(`docs/aws-infra.md`).

## Notes / limits

- `requirements-lambda.txt` is intentionally minimal. If a runtime `ImportError`
  appears in CloudWatch, add the missing package here (or temporarily build
  from `requirements.txt`) and rebuild.
- `psycopg2-binary` ships manylinux wheels compatible with the Lambda base
  image; no system build deps needed.
- Image is `linux/amd64`. On Apple Silicon, build with
  `docker build --platform linux/amd64 ...`.
