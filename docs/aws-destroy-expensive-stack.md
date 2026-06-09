# Destroy the Expensive AWS Stack

The Terraform module at `infra/aws/` provisions RDS PostgreSQL, App Runner,
Secrets Manager, ECR, and VPC infrastructure that costs roughly **$18–$40+ per
month**. The free-tier deployment in `infra/aws-free-tier/` does **not** require
any of it.

If you applied `infra/aws/` previously (a local `terraform.tfstate` file is
present), follow this guide to destroy the stack and stop the bleed.

---

## 1. Verify what is currently deployed

```powershell
cd C:\Users\super\buff163.price-checker-main\buff163.price-checker\infra\aws
aws sts get-caller-identity --output table
terraform state list
```

If `terraform state list` returns an empty result, nothing is deployed in this
account/region for this stack — you can skip the rest.

If the list contains resources, continue below.

## 2. Estimate current monthly spend

```powershell
$start = (Get-Date -Day 1).ToString('yyyy-MM-dd')
$end   = (Get-Date).ToString('yyyy-MM-dd')
aws ce get-cost-and-usage `
  --time-period Start=$start,End=$end `
  --granularity MONTHLY `
  --metrics "UnblendedCost" `
  --group-by Type=DIMENSION,Key=SERVICE `
  --output table
```

Look for `Amazon Relational Database Service`, `AWS App Runner`,
`Amazon Elastic Load Balancing`, `Amazon Elastic Container Service`, and
`AWS Secrets Manager`. Sum those to see what destroying this stack will save.

## 3. Back up before destroy (optional, only if RDS holds data you want)

If the RDS instance contains scraper history you want to keep:

```powershell
aws rds describe-db-instances --query "DBInstances[].DBInstanceIdentifier" --output table
$instance = "<from-above>"
aws rds create-db-snapshot `
  --db-instance-identifier $instance `
  --db-snapshot-identifier "buff163-final-snapshot-$(Get-Date -Format yyyyMMdd-HHmm)"
```

The snapshot is **manual** (not auto-deleted) and is charged at $0.095/GB-month.
A 20 GB snapshot is ~$1.90/month. Delete it once you are sure the data is no
longer needed:

```powershell
aws rds delete-db-snapshot --db-snapshot-identifier <id>
```

## 4. Destroy

```powershell
cd C:\Users\super\buff163.price-checker-main\buff163.price-checker\infra\aws
terraform destroy
```

Terraform will list every resource to delete. Review carefully, then type `yes`.

Expected resources to be destroyed:
- `aws_db_instance.scraper` (RDS PostgreSQL)
- `aws_apprunner_service.dashboard` (App Runner)
- `aws_ecr_repository.scraper`, `aws_ecr_repository.dashboard`
- `aws_secretsmanager_secret.*`
- `aws_lambda_function.scraper`
- `aws_scheduler_schedule.scraper`
- `aws_cloudwatch_log_group.*`
- `aws_vpc.main` and all subnets/route tables/security groups
- IAM roles/policies for the above

## 5. Verify nothing leaked

After `terraform destroy` finishes, double-check no expensive resources remain
in the account/region:

```powershell
aws rds describe-db-instances --query "length(DBInstances)"
aws apprunner list-services --query "length(ServiceSummaryList)"
aws ecs list-clusters --query "length(clusterArns)"
aws elbv2 describe-load-balancers --query "length(LoadBalancers)"
aws ec2 describe-nat-gateways --filter Name=state,Values=available --query "length(NatGateways)"
aws ec2 describe-addresses --query "length(Addresses)"
aws ec2 describe-instances --filter Name=instance-state-name,Values=running --query "length(Reservations)"
```

Every command above should return `0`. If any return non-zero, investigate
those resources individually — they may be from another project.

Also check ECR for orphaned images:

```powershell
aws ecr describe-repositories --query "repositories[].repositoryName"
```

If `buff163-scraper` or `buff163-dashboard` still exist (Terraform leaves
repos with images by default), empty + delete:

```powershell
aws ecr list-images --repository-name buff163-scraper --query 'imageIds[*]' --output json | `
  ForEach-Object { aws ecr batch-delete-image --repository-name buff163-scraper --image-ids "$_" }
aws ecr delete-repository --repository-name buff163-scraper --force
```

## 6. Remove local Terraform state

After destroy completes successfully, the local state files become useless and
sensitive (they contained DB endpoints, ARNs, possibly secret values).

```powershell
Remove-Item infra\aws\terraform.tfstate -Force
Remove-Item infra\aws\terraform.tfstate.backup -Force
```

Do **not** commit these files; they are already in `.gitignore` if configured
correctly, but verify with `git status` first.

## 7. Disable the expensive stack from future accidental re-apply

To prevent accidental re-deploy:

Option A — delete the module directory entirely (recommended if you have no
plans to use it):
```powershell
Remove-Item -Recurse -Force infra\aws
```

Option B — keep the code but rename the directory so `terraform apply` cannot
be run without renaming back:
```powershell
Rename-Item infra\aws infra\aws.archived
```

The free-tier deployment in `infra/aws-free-tier/` is independent and continues
to work either way.

## 8. Confirm the bill drops

Check AWS Billing dashboard 24–48 hours after destroy. Expect:
- RDS, App Runner, ELB, ECS, Secrets Manager → trending to $0
- Lambda, EventBridge, Logs, S3, SSM → already $0 (free tier)

Set up a Cost Anomaly Detection monitor with email subscription to catch
unexpected spend:

```powershell
aws ce create-anomaly-monitor --anomaly-monitor `
  '{"MonitorName":"buff163-anomaly","MonitorType":"DIMENSIONAL","MonitorDimension":"SERVICE"}'
```

Then create a subscription tying that monitor to your email.

---

## Summary

After running this guide:
- Expensive stack: deleted (~$18–$75/month saved)
- Local state files: deleted
- Free-tier stack (`infra/aws-free-tier/`): untouched, still $0/month
- Streamlit Cloud dashboard: untouched, still $0
- Local CLI + GitHub Actions: untouched
