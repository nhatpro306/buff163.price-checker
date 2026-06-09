# AWS Free Tier Deployment

This deployment is designed for very small personal usage with no always-on paid
compute.

## Architecture

- Lambda scrapes the public CSGO Trader BUFF163 price feed once per day.
- Lambda writes `index.html` and `data.json` to a private S3 bucket.
- CloudFront serves the static dashboard over HTTPS.
- EventBridge Scheduler triggers the Lambda.

This stack intentionally does not use RDS, NAT Gateway, App Runner, ECS, ALB, or
ECR.

## Deploy

```powershell
cd infra/aws-free-tier
terraform init
terraform apply -auto-approve -var="aws_region=us-east-1"
terraform output cloudfront_url
```

To create an AWS Budget email alert at the same time:

```powershell
terraform apply -auto-approve `
  -var="aws_region=us-east-1" `
  -var="budget_alert_email=you@example.com" `
  -var="monthly_budget_usd=1.00"
```

Run the scraper immediately:

```powershell
aws lambda invoke `
  --function-name (terraform output -raw lambda_function_name) `
  --payload "{}" `
  --cli-binary-format raw-in-base64-out `
  --region us-east-1 `
  lambda-output.json
Get-Content lambda-output.json
```

## Free Tier Boundaries

Keep usage small:

- Schedule no more than once per day unless you have checked current AWS Free
  Tier usage.
- Do not enable RDS, NAT Gateway, App Runner, ECS, ALB, or ECR for this mode.
- Keep S3 objects small and avoid frequent CloudFront invalidations.
- Keep CloudWatch log retention short.
- Set AWS Budgets and Billing alarms before sharing the dashboard publicly.

Free Tier is not a guarantee of a zero bill. It depends on account age, current
AWS Free Tier program terms, region, and monthly usage.

## Current Low-Cost Shape

This stack should only contain:

- one private S3 bucket with `index.html` and `data.json`
- one CloudFront distribution using `PriceClass_100`
- one Lambda function scheduled once per day
- one EventBridge Scheduler schedule
- one CloudWatch log group with short retention

If you see RDS, NAT Gateway, App Runner, ECS, ALB, ECR images, EC2 instances, or
Elastic IPs for this project, delete them unless you intentionally moved back to
the paid production architecture.
