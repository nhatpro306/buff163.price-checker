# AWS Infrastructure (Terraform)

Repeatable IaC for the AWS production stack. Files live in `infra/aws/`.

## Resources Created

| Resource | Purpose |
|----------|---------|
| `aws_vpc`, subnets, NAT, routes | Private network for RDS plus outbound internet for Lambda/App Runner. |
| `aws_db_instance` | Private RDS PostgreSQL with an RDS-managed master password in Secrets Manager. |
| `aws_ecr_repository.scraper` | Holds the Lambda container image with scan-on-push. |
| `aws_ecr_repository.dashboard` | Holds the Streamlit dashboard image with scan-on-push. |
| `aws_lambda_function` | Runs `handler.lambda_handler`. |
| `aws_apprunner_service` | Runs the Streamlit dashboard from ECR. |
| `aws_iam_role` and policies | Least-privilege Lambda, scheduler, and App Runner permissions. |
| `aws_cloudwatch_log_group` | `/aws/lambda/<name>`, configurable retention. |
| `aws_scheduler_schedule` | EventBridge Scheduler on `schedule_expression`. |

## What Is Not Hardcoded

- Account ID is resolved with `aws_caller_identity`.
- Secret values are not committed and should not be placed in `terraform.tfvars`.
- Terraform creates placeholder Secrets Manager secrets for `DATABASE_URL` and `BUFF_COOKIE` when external ARNs are not supplied.
- The app receives `DATABASE_URL_SECRET_ARN` and `BUFF_COOKIE_SECRET_ARN`; values are fetched at runtime.

## Variables

See `infra/aws/variables.tf`. Key groups:

- Region and naming: `aws_region`, `project`.
- Images: `ecr_repo_name`, `dashboard_ecr_repo_name`, `image_tag`, `dashboard_image_tag`.
- Lambda: `lambda_function_name`, `lambda_memory_mb`, `lambda_timeout_seconds`.
- Schedule: `schedule_expression`, `schedule_enabled`.
- RDS: `db_name`, `db_username`, `db_instance_class`, storage, backup, and deletion-protection settings.
- Dashboard: `dashboard_service_name`, `dashboard_cpu`, `dashboard_memory`, `dashboard_env`.
- Secrets: `database_url_secret_arn`, `buff_cookie_secret_arn`, `secret_arns`.

Copy `terraform.tfvars.example` to `terraform.tfvars` and edit non-secret values.

## Deploy

For the full beginner workflow, use `DEPLOYMENT_AWS.md`.

Short form:

```bash
cd infra/aws
terraform init

# Create ECR first.
terraform apply -target=aws_ecr_repository.scraper -target=aws_ecr_repository.dashboard

# Build and push both images, then populate DATABASE_URL in Secrets Manager.

# Apply the full stack.
terraform apply
```

Update deployment with a new image tag:

```bash
terraform apply -var="image_tag=<new-tag>" -var="dashboard_image_tag=<new-tag>"
```

Check Lambda logs:

```bash
aws logs tail "$(terraform output -raw log_group_name)" --follow
```

## Rollback

```bash
# Re-point services to a previous known-good image tag.
terraform apply -var="image_tag=<previous-good-tag>" -var="dashboard_image_tag=<previous-good-tag>"

# Disable the schedule without destroying anything.
terraform apply -var="schedule_enabled=false"
```

## Notes

- RDS is private. Run migrations from a network path that can reach the VPC.
- `BUFF_AUTO_MIGRATE_POSTGRES=1` lets Lambda/App Runner apply pending migrations at startup after `DATABASE_URL` is populated.
- The NAT gateway lets Lambda and App Runner reach BUFF163 while keeping RDS private.
- Lambda's 15-minute maximum runtime remains the main reason to move the scraper to ECS Fargate later.
