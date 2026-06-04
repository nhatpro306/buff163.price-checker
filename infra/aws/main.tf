data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id          = data.aws_caller_identity.current.account_id
  scraper_image_uri   = "${local.account_id}.dkr.ecr.${data.aws_region.current.region}.amazonaws.com/${var.ecr_repo_name}:${var.image_tag}"
  dashboard_image_uri = "${local.account_id}.dkr.ecr.${data.aws_region.current.region}.amazonaws.com/${var.dashboard_ecr_repo_name}:${var.dashboard_image_tag}"

  database_url_secret_arn = var.database_url_secret_arn != "" ? var.database_url_secret_arn : aws_secretsmanager_secret.database_url.arn
  buff_cookie_secret_arn  = var.buff_cookie_secret_arn != "" ? var.buff_cookie_secret_arn : aws_secretsmanager_secret.buff_cookie.arn
  allowed_secret_arns     = distinct(compact(concat(var.secret_arns, [local.database_url_secret_arn, local.buff_cookie_secret_arn])))

  # Secret-ARN env vars passed to the Lambda (values resolved at runtime by the
  # app via the Secrets Manager loader). Empty ARNs are omitted.
  secret_env = merge(
    local.database_url_secret_arn == "" ? {} : { DATABASE_URL_SECRET_ARN = local.database_url_secret_arn },
    local.buff_cookie_secret_arn == "" ? {} : { BUFF_COOKIE_SECRET_ARN = local.buff_cookie_secret_arn },
  )
}

# --- Network ---------------------------------------------------------------
data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project}-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project}-igw"
  }
}

resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project}-public-${count.index + 1}"
  }
}

resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "${var.project}-private-${count.index + 1}"
  }
}

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "${var.project}-nat-eip"
  }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name = "${var.project}-nat"
  }

  depends_on = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project}-public-rt"
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = {
    Name = "${var.project}-private-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# --- ECR -------------------------------------------------------------------
resource "aws_ecr_repository" "scraper" {
  name                 = var.ecr_repo_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "dashboard" {
  name                 = var.dashboard_ecr_repo_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- Secrets ---------------------------------------------------------------
resource "aws_secretsmanager_secret" "database_url" {
  name        = "${var.project}/DATABASE_URL"
  description = "PostgreSQL DATABASE_URL for the BUFF163 app. Set the value after RDS is created."
}

resource "aws_secretsmanager_secret" "buff_cookie" {
  name        = "${var.project}/BUFF_COOKIE"
  description = "Optional BUFF163 session cookie. Set only if scraping requires it."
}

# --- CloudWatch Logs -------------------------------------------------------
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = var.log_retention_days
}

# --- RDS PostgreSQL --------------------------------------------------------
resource "aws_security_group" "lambda" {
  name        = "${var.project}-lambda-sg"
  description = "Lambda scraper outbound access"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "apprunner" {
  name        = "${var.project}-apprunner-sg"
  description = "App Runner VPC connector outbound access"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.project}-rds-sg"
  description = "Private PostgreSQL access from Lambda and App Runner"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id, aws_security_group.apprunner.id]
  }
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "postgres" {
  identifier                      = "${var.project}-postgres"
  engine                          = "postgres"
  engine_version                  = "16"
  instance_class                  = var.db_instance_class
  allocated_storage               = var.db_allocated_storage_gb
  db_name                         = var.db_name
  username                        = var.db_username
  manage_master_user_password     = true
  db_subnet_group_name            = aws_db_subnet_group.main.name
  vpc_security_group_ids          = [aws_security_group.rds.id]
  publicly_accessible             = false
  backup_retention_period         = var.db_backup_retention_days
  deletion_protection             = var.db_deletion_protection
  skip_final_snapshot             = var.db_skip_final_snapshot
  final_snapshot_identifier       = "${var.project}-postgres-final"
  performance_insights_enabled    = true
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
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
    for_each = length(local.allowed_secret_arns) > 0 ? [1] : []
    content {
      sid       = "ReadSecrets"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = local.allowed_secret_arns
    }
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.project}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# --- Lambda (container image) ---------------------------------------------
resource "aws_lambda_function" "scraper" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = local.scraper_image_uri
  memory_size   = var.lambda_memory_mb
  timeout       = var.lambda_timeout_seconds

  environment {
    variables = merge(var.extra_env, local.secret_env)
  }

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# --- App Runner dashboard --------------------------------------------------
data "aws_iam_policy_document" "apprunner_ecr_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["build.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apprunner_ecr_access" {
  name               = "${var.project}-apprunner-ecr-role"
  assume_role_policy = data.aws_iam_policy_document.apprunner_ecr_assume.json
}

resource "aws_iam_role_policy_attachment" "apprunner_ecr_access" {
  role       = aws_iam_role.apprunner_ecr_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

data "aws_iam_policy_document" "apprunner_instance_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["tasks.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apprunner_instance" {
  name               = "${var.project}-apprunner-instance-role"
  assume_role_policy = data.aws_iam_policy_document.apprunner_instance_assume.json
}

data "aws_iam_policy_document" "apprunner_instance_permissions" {
  statement {
    sid       = "ReadSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = local.allowed_secret_arns
  }
}

resource "aws_iam_role_policy" "apprunner_instance" {
  name   = "${var.project}-apprunner-instance-policy"
  role   = aws_iam_role.apprunner_instance.id
  policy = data.aws_iam_policy_document.apprunner_instance_permissions.json
}

resource "aws_apprunner_vpc_connector" "dashboard" {
  vpc_connector_name = "${var.project}-dashboard-vpc"
  subnets            = aws_subnet.private[*].id
  security_groups    = [aws_security_group.apprunner.id]
}

resource "aws_apprunner_service" "dashboard" {
  service_name = var.dashboard_service_name

  source_configuration {
    auto_deployments_enabled = false

    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_ecr_access.arn
    }

    image_repository {
      image_identifier      = local.dashboard_image_uri
      image_repository_type = "ECR"

      image_configuration {
        port                          = "8501"
        runtime_environment_variables = merge(var.dashboard_env, local.secret_env)
      }
    }
  }

  instance_configuration {
    cpu               = var.dashboard_cpu
    memory            = var.dashboard_memory
    instance_role_arn = aws_iam_role.apprunner_instance.arn
  }

  network_configuration {
    egress_configuration {
      egress_type       = "VPC"
      vpc_connector_arn = aws_apprunner_vpc_connector.dashboard.arn
    }
  }
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
