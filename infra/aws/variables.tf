variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-southeast-1"
}

variable "project" {
  description = "Name prefix for created resources."
  type        = string
  default     = "buff163-scraper"
}

variable "ecr_repo_name" {
  description = "ECR repository holding the Lambda container image."
  type        = string
  default     = "buff163-scraper"
}

variable "image_tag" {
  description = "Container image tag to deploy (e.g. a git SHA or 'latest')."
  type        = string
  default     = "latest"
}

variable "lambda_function_name" {
  description = "Lambda function name."
  type        = string
  default     = "buff163-scraper"
}

variable "lambda_memory_mb" {
  description = "Lambda memory size in MB."
  type        = number
  default     = 1024
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds (max 900 for Lambda)."
  type        = number
  default     = 900
}

variable "schedule_expression" {
  description = "EventBridge Scheduler expression, e.g. 'rate(12 hours)' or 'cron(0 0,12 * * ? *)'."
  type        = string
  default     = "rate(12 hours)"
}

variable "schedule_enabled" {
  description = "Whether the schedule is enabled."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention in days."
  type        = number
  default     = 30
}

# Secret ARNs (created/managed OUTSIDE this stack so values never enter
# Terraform state). The Lambda is granted GetSecretValue on exactly these.
variable "secret_arns" {
  description = "ARNs of Secrets Manager secrets the Lambda may read (DATABASE_URL, BUFF_COOKIE, optional Google creds)."
  type        = list(string)
  default     = []
}

# Names of the secrets, passed to the Lambda as *_SECRET_ARN-style env so the
# app can fetch them at runtime. No secret VALUES are set here.
variable "database_url_secret_arn" {
  description = "Secrets Manager ARN for the Postgres DATABASE_URL."
  type        = string
  default     = ""
}

variable "buff_cookie_secret_arn" {
  description = "Secrets Manager ARN for the BUFF163 cookie."
  type        = string
  default     = ""
}

variable "extra_env" {
  description = "Additional non-secret environment variables for the Lambda."
  type        = map(string)
  default = {
    STORAGE_BACKEND          = "postgres"
    BUFF_REQUEST_TIMEOUT     = "15"
    BUFF_MAX_RETRIES         = "3"
    BUFF_BACKOFF_BASE_SECONDS = "1"
  }
}
