# AWS Secrets & Config Handling

How the scraper resolves sensitive config locally and on AWS, and how secrets
are kept out of logs.

## Secrets inventory

| Secret | Used when | Local env | Lambda (Secrets Manager) |
|--------|-----------|-----------|--------------------------|
| `DATABASE_URL` | `STORAGE_BACKEND=postgres` | `DATABASE_URL` | `DATABASE_URL_SECRET_ARN` |
| `BUFF_COOKIE` | optional, recommended if BUFF returns 403 | `BUFF_COOKIE` | `BUFF_COOKIE_SECRET_ARN` |
| `GSHEET_CREDS_JSON` | `STORAGE_BACKEND=sheets` | `GSHEET_CREDS_JSON` | secret ARN (future) |
| `DISCORD_WEBHOOK_URL` | alerts (future) | `DISCORD_WEBHOOK_URL` | secret ARN (future) |

## Resolution order (`src/secrets.py`)

For any name (e.g. `DATABASE_URL`), `get_secret` resolves:

1. **Direct env var** `DATABASE_URL` — local dev, GitHub Actions secrets.
2. **`DATABASE_URL_SECRET_ARN`** env → fetched from AWS Secrets Manager (Lambda
   runtime provides `boto3`; imported lazily so local/CI need not install it).
3. **Default** (or `require_secret` raises a clear, value-free error).

The fetched value is written back into `os.environ` so existing code
(`os.getenv("DATABASE_URL")` in the Postgres store) works unchanged. The Lambda
handler calls `hydrate_secrets(("DATABASE_URL", "BUFF_COOKIE"))` before each run.
The Streamlit dashboard hydrates `DATABASE_URL` on startup when
`STORAGE_BACKEND=postgres`.

## Redaction (`src/redaction.py`)

`redact_secrets(text)` masks before anything is logged or returned:

- exact values of known secret env vars (`SECRET_ENV_KEYS`),
- URL credentials: `scheme://user:pass@host` → `scheme://***:***@host`,
- Discord webhook URLs.

The Lambda handler runs all error messages through `redact_secrets` before
returning them, so CloudWatch never sees a raw DSN, cookie, or webhook.

## Rules

- `.env.example` holds **placeholders only**. Real `.env` is git-ignored.
- Never log secret values. Use `redact_secrets` on any message that could embed
  config (DSN errors, request context).
- IAM grants the Lambda `secretsmanager:GetSecretValue` on **only** the listed
  secret ARNs (`infra/aws/`), never `*`.
- Secret **values** never enter Terraform state — only ARNs are referenced.

## Creating the secrets (one-time)

```bash
aws secretsmanager create-secret --name buff163/DATABASE_URL \
  --secret-string "postgresql://USER:PASS@HOST:5432/DB"
aws secretsmanager create-secret --name buff163/BUFF_COOKIE \
  --secret-string "session=...; csrf_token=..."
```

Then pass the resulting ARNs to Terraform (`database_url_secret_arn`,
`buff_cookie_secret_arn`, `secret_arns`) or let Terraform create placeholder
secrets and set their values with `aws secretsmanager put-secret-value` after
RDS exists. See `DEPLOYMENT_AWS.md`.

## Rotation

Update the secret value in Secrets Manager; no redeploy needed (the handler
fetches per invocation). Rotate `BUFF_COOKIE` whenever BUFF163 sessions expire.
