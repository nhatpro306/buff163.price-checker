# AWS Infrastructure (Terraform)

Repeatable IaC for the scheduled scraper Lambda. Files live in `infra/aws/`.

## Resources created

| Resource | Purpose |
|----------|---------|
| `aws_ecr_repository` | Holds the Lambda container image (scan-on-push). |
| `aws_lambda_function` (Image) | Runs `handler.lambda_handler`. |
| `aws_iam_role` (lambda) + policy | Least privilege: write its own log group + `GetSecretValue` on listed secret ARNs only. |
| `aws_cloudwatch_log_group` | `/aws/lambda/<name>`, configurable retention. |
| `aws_iam_role` (scheduler) + policy | Allows EventBridge Scheduler to invoke only this function. |
| `aws_scheduler_schedule` | EventBridge Scheduler on `schedule_expression`. |

## What is NOT hardcoded

- **Account ID** — resolved at apply via `aws_caller_identity`.
- **Secret values** — only secret **ARNs** are passed (as `*_SECRET_ARN` env);
  the app fetches values at runtime (see `docs/aws-secrets.md`). Values never
  enter Terraform state.
- **Database URL / tokens / cookies** — never in `.tf` or `.tfvars` committed
  files. `terraform.tfvars` is git-ignored.

## Variables

See `infra/aws/variables.tf`. Key ones: `aws_region`, `ecr_repo_name`,
`image_tag`, `lambda_function_name`, `lambda_memory_mb`,
`lambda_timeout_seconds`, `schedule_expression`, `secret_arns`,
`database_url_secret_arn`, `buff_cookie_secret_arn`.

Copy `terraform.tfvars.example` → `terraform.tfvars` and edit.

## Deploy

Prereq: build + push the image first (see `docs/aws-container-deploy.md`); the
Lambda needs an existing image at `image_tag`. The ECR repo can be created by
this stack first, then push, then apply again — or create ECR out of band.

```bash
cd infra/aws
terraform init

# 1) Create just the ECR repo (so you have somewhere to push):
terraform apply -target=aws_ecr_repository.scraper

# 2) Build + push image (docs/aws-container-deploy.md), set image_tag accordingly.

# 3) Apply the rest:
terraform apply
```

Update deployment (new image):

```bash
# push new image tag, then:
terraform apply -var="image_tag=<new-tag>"
# or update the function image directly:
aws lambda update-function-code \
  --function-name "$(terraform output -raw lambda_function_name)" \
  --image-uri "<ecr-url>:<new-tag>"
```

Check logs:

```bash
aws logs tail "$(terraform output -raw log_group_name)" --follow
```

## Rollback

```bash
# Re-point Lambda to a previous known-good image tag:
terraform apply -var="image_tag=<previous-good-tag>"

# Disable the schedule without destroying anything:
terraform apply -var="schedule_enabled=false"

# Full teardown (careful — removes ECR repo + images + function + schedule):
terraform destroy
```

## Notes

- `flexible_time_window=OFF` and `maximum_retry_attempts=0` keep runs
  predictable and avoid overlapping/duplicate invocations. Storage upsert makes
  re-runs idempotent regardless.
- Alternative to Terraform: an AWS SAM template or documented AWS CLI sequence —
  Terraform chosen as the simplest maintainable option since the repo had no
  prior IaC.
- For the ECS Fargate fallback (if Lambda 15-min limit is exceeded), this stack
  would be swapped for an ECS task definition + scheduled task; not included
  unless needed (see `docs/aws-deploy-readiness.md`).
