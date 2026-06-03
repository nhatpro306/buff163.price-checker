data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  image_uri  = "${local.account_id}.dkr.ecr.${data.aws_region.current.region}.amazonaws.com/${var.ecr_repo_name}:${var.image_tag}"

  # Secret-ARN env vars passed to the Lambda (values resolved at runtime by the
  # app via the Secrets Manager loader). Empty ARNs are omitted.
  secret_env = merge(
    var.database_url_secret_arn == "" ? {} : { DATABASE_URL_SECRET_ARN = var.database_url_secret_arn },
    var.buff_cookie_secret_arn == "" ? {} : { BUFF_COOKIE_SECRET_ARN = var.buff_cookie_secret_arn },
  )
}

# --- ECR -------------------------------------------------------------------
resource "aws_ecr_repository" "scraper" {
  name                 = var.ecr_repo_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- CloudWatch Logs -------------------------------------------------------
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = var.log_retention_days
}

# --- IAM: Lambda execution role (least privilege) --------------------------
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

data "aws_iam_policy_document" "lambda_permissions" {
  # Scoped log access to this function's log group only.
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  # Read only the explicitly listed secrets.
  dynamic "statement" {
    for_each = length(var.secret_arns) > 0 ? [1] : []
    content {
      sid       = "ReadSecrets"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = var.secret_arns
    }
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.project}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# --- Lambda (container image) ---------------------------------------------
resource "aws_lambda_function" "scraper" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = local.image_uri
  memory_size   = var.lambda_memory_mb
  timeout       = var.lambda_timeout_seconds

  environment {
    variables = merge(var.extra_env, local.secret_env)
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# --- EventBridge Scheduler -------------------------------------------------
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

data "aws_iam_policy_document" "scheduler_invoke" {
  statement {
    sid       = "InvokeLambda"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.scraper.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${var.project}-scheduler-policy"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_invoke.json
}

resource "aws_scheduler_schedule" "scraper" {
  name       = "${var.project}-schedule"
  group_name = "default"
  state      = var.schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = var.schedule_expression

  target {
    arn      = aws_lambda_function.scraper.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}
