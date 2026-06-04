# AWS Production Deployment

This guide deploys the whole project on AWS:

- Streamlit dashboard: Docker image on AWS App Runner.
- Scraper scheduler: Docker image on AWS Lambda, triggered by EventBridge Scheduler.
- Database: private Amazon RDS PostgreSQL.
- Secrets: AWS Secrets Manager.
- Logs: CloudWatch Logs for Lambda and App Runner service logs.
- Infrastructure: Terraform in `infra/aws/`.

No secret values are committed. Terraform creates secret placeholders, but you add the values with AWS CLI after RDS exists.

## Prerequisites

Install AWS CLI, Terraform `>= 1.5`, Docker, and Python 3.11.

```powershell
aws sts get-caller-identity
terraform version
docker version
```

## 1. Local SQLite Check

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$env:STORAGE_BACKEND = "sqlite"
$env:BUFF_SQLITE_PATH = "buff163.sqlite3"
$env:BUFF_SKIP_DIRECT = "1"
$env:BUFF_FALLBACK_CSGOTRADER = "0"
$env:BUFF_FULL_CATALOG = "0"
python main.py
streamlit run app.py
```

## 2. Configure Terraform

```powershell
Copy-Item infra\aws\terraform.tfvars.example infra\aws\terraform.tfvars
notepad infra\aws\terraform.tfvars
```

Keep real secret values out of this file.

## 3. Create ECR, Build, And Push Images

```powershell
.\scripts\deploy_aws.ps1 -Region ap-southeast-1
```

The script creates the two ECR repositories first, then builds and pushes the Lambda scraper and Streamlit dashboard images.

## 4. Create RDS And Secret Placeholders

```powershell
cd infra\aws
terraform apply `
  -target=aws_vpc.main `
  -target=aws_db_instance.postgres `
  -target=aws_secretsmanager_secret.database_url `
  -target=aws_secretsmanager_secret.buff_cookie
```

Get outputs:

```powershell
$dbHost = terraform output -raw rds_endpoint
$dbName = terraform output -raw rds_database_name
$dbSecretArn = terraform output -raw database_url_secret_arn
$rdsMasterSecretArn = terraform output -raw rds_master_secret_arn
```

Read the RDS-managed username/password JSON:

```powershell
aws secretsmanager get-secret-value `
  --secret-id $rdsMasterSecretArn `
  --query SecretString `
  --output text
```

Store the final app DSN in Secrets Manager:

```powershell
aws secretsmanager put-secret-value `
  --secret-id $dbSecretArn `
  --secret-string "postgresql://USERNAME:PASSWORD@$dbHost:5432/$dbName"
```

If BUFF requires a session cookie:

```powershell
$cookieSecretArn = terraform output -raw buff_cookie_secret_arn
aws secretsmanager put-secret-value `
  --secret-id $cookieSecretArn `
  --secret-string "session=...; csrf_token=..."
```

## 5. Apply Full Infrastructure

```powershell
terraform apply
```

This creates or updates RDS PostgreSQL, Lambda, EventBridge Scheduler, App Runner, IAM roles, security groups, ECR, and CloudWatch logging.

## 6. PostgreSQL Migrations

Production defaults set `BUFF_AUTO_MIGRATE_POSTGRES=1`, so Lambda and App Runner apply pending `db/migrations/*.sql` files when the PostgreSQL backend starts. This keeps the first scraper/dashboard startup reproducible after `DATABASE_URL` is populated.

For manual verification or troubleshooting, run migrations from a machine that can reach the private RDS endpoint, such as an EC2 instance in the VPC:

```powershell
python -m pip install -r requirements.txt
$env:DATABASE_URL = "postgresql://USERNAME:PASSWORD@RDS_ENDPOINT:5432/DB_NAME"
python scripts\apply_postgres_migrations.py
```

Optional import of existing history:

```powershell
python scripts\import_existing_data_to_postgres.py --sqlite buff163.sqlite3
python scripts\import_existing_data_to_postgres.py --csv history_export.csv
```

## 7. Smoke Test Lambda

```powershell
aws lambda invoke `
  --function-name (terraform output -raw lambda_function_name) `
  --payload "{ `"mode`": `"health_check`" }" `
  response.json
Get-Content response.json
```

Run one real scrape:

```powershell
aws lambda invoke `
  --function-name (terraform output -raw lambda_function_name) `
  --payload "{}" `
  scrape-response.json
Get-Content scrape-response.json
```

## 8. Open Dashboard

```powershell
terraform output -raw dashboard_service_url
```

## 9. Logs And Monitoring

Lambda logs:

```powershell
aws logs tail (terraform output -raw log_group_name) --follow
```

App Runner logs are visible in CloudWatch Logs under the App Runner service log streams. The dashboard prints its selected storage backend during startup.

The scraper returns structured Lambda JSON and logs status, item counts, backend, and duration. PostgreSQL runs are recorded in `scraper_runs`, and schema/runtime metadata is tracked in `tracking_metadata`.

## Updating Production

```powershell
.\scripts\deploy_aws.ps1 -Region ap-southeast-1 -ImageTag <git-sha> -ApplyInfrastructure
```

## Remaining Operational Notes

- RDS is private. Run migrations/imports from a network path that can reach it.
- Lambda has a 15-minute maximum runtime. If full catalog scraping outgrows that, move the scraper to ECS Fargate scheduled tasks.
- Secret values are not stored in Terraform, so populate `DATABASE_URL` before expecting healthy services.
