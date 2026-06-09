data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  bucket_name = "${var.project}-${data.aws_caller_identity.current.account_id}-${data.aws_region.current.region}"
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/build/static_site_handler.zip"

  # Lambda entry.
  source {
    content  = file("${path.module}/../../static_site_handler.py")
    filename = "static_site_handler.py"
  }

  # Shared helpers (S3 dedupe, alerts, sheets, config).
  # Empty src/__init__.py stub: the real src/__init__.py imports heavy modules
  # (pandas, gspread, etc.) that are not in the Lambda zip. Use a stub so
  # `from src.aws_lambda.X import Y` resolves without pulling those imports.
  source {
    content  = "# stub init for Lambda zip\n"
    filename = "src/__init__.py"
  }
  source {
    content  = file("${path.module}/../../src/aws_lambda/__init__.py")
    filename = "src/aws_lambda/__init__.py"
  }
  source {
    content  = file("${path.module}/../../src/aws_lambda/config.py")
    filename = "src/aws_lambda/config.py"
  }
  source {
    content  = file("${path.module}/../../src/aws_lambda/s3_store.py")
    filename = "src/aws_lambda/s3_store.py"
  }
  source {
    content  = file("${path.module}/../../src/aws_lambda/alerts.py")
    filename = "src/aws_lambda/alerts.py"
  }
  source {
    content  = file("${path.module}/../../src/aws_lambda/handler_sheets.py")
    filename = "src/aws_lambda/handler_sheets.py"
  }
  source {
    content  = file("${path.module}/../../src/aws_lambda/buff_listings.py")
    filename = "src/aws_lambda/buff_listings.py"
  }
}

resource "aws_s3_bucket" "site" {
  bucket = local.bucket_name
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.project}-oac"
  description                       = "Private S3 access for BUFF163 free-tier static site"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  comment             = "${var.project} static dashboard"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "site"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "site"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    default_ttl            = 300
    max_ttl                = 300
    min_ttl                = 0

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

data "aws_iam_policy_document" "site_bucket" {
  statement {
    sid     = "AllowCloudFrontRead"
    actions = ["s3:GetObject"]

    resources = ["${aws_s3_bucket.site.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = data.aws_iam_policy_document.site_bucket.json
}

resource "aws_cloudwatch_log_group" "scraper" {
  name              = "/aws/lambda/${var.project}-static-scraper"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid = "WriteStaticSite"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:HeadObject",
    ]
    resources = ["${aws_s3_bucket.site.arn}/*"]
  }

  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.scraper.arn}:*"]
  }

  statement {
    sid     = "ReadConfigSecrets"
    actions = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [
      "arn:aws:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter/buff163/*",
    ]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.project}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_lambda_function" "scraper" {
  function_name                  = "${var.project}-static-scraper"
  role                           = aws_iam_role.lambda.arn
  runtime                        = "python3.11"
  handler                        = "static_site_handler.lambda_handler"
  filename                       = data.archive_file.lambda_zip.output_path
  source_code_hash               = data.archive_file.lambda_zip.output_base64sha256
  memory_size                    = var.lambda_memory_mb
  timeout                        = var.lambda_timeout_seconds
  reserved_concurrent_executions = var.lambda_reserved_concurrency

  environment {
    variables = {
      STATIC_SITE_BUCKET        = aws_s3_bucket.site.bucket
      S3_BUCKET                 = aws_s3_bucket.site.bucket
      AWS_REGION_HINT           = data.aws_region.current.region
      BUFF_TRACK_KEYWORDS       = var.track_keywords
      BUFF_MIN_PRICE_CNY        = "0"
      LOG_LEVEL                 = var.log_level
      REQUEST_TIMEOUT_SECONDS   = tostring(var.request_timeout_seconds)
      MAX_RETRIES               = tostring(var.max_retries)
      WRITE_SHEETS              = var.write_sheets ? "1" : "0"
      SPREADSHEET_ID            = var.spreadsheet_id
      WORKSHEET_NAME            = var.worksheet_name
      GOOGLE_CREDS_SSM_PARAM    = var.google_creds_ssm_param
      DISCORD_WEBHOOK_SSM_PARAM = var.discord_webhook_ssm_param
      BUFF_COOKIE_SSM_PARAM     = var.buff_cookie_ssm_param
      LISTING_PAGES             = tostring(var.listing_pages)
    }
  }

  depends_on = [aws_cloudwatch_log_group.scraper]
}

# --- S3 lifecycle: cap storage growth from history/ and raw/ ---------------
resource "aws_s3_bucket_lifecycle_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    id     = "expire-raw"
    status = "Enabled"
    filter {
      prefix = "raw/"
    }
    expiration {
      days = var.raw_keep_days
    }
  }

  rule {
    id     = "expire-history"
    status = "Enabled"
    filter {
      prefix = "history/"
    }
    expiration {
      days = var.history_keep_days
    }
  }

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_scheduler_schedule" "scraper" {
  name       = "${var.project}-daily-scrape"
  group_name = "default"
  state      = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = var.schedule_expression

  target {
    arn      = aws_lambda_function.scraper.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_retry_attempts = 1
    }
  }
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.project}-scheduler-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "InvokeLambda"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.scraper.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${var.project}-scheduler-policy"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_budgets_budget" "monthly_cost_guardrail" {
  count = var.budget_alert_email == "" ? 0 : 1

  name         = "${var.project}-monthly-cost-guardrail"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
