variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-southeast-1"
}

variable "project" {
  description = "Name prefix for created resources."
  type        = string
  default     = "buff163"
}

variable "ecr_repo_name" {
  description = "ECR repository holding the Lambda container image."
  type        = string
  default     = "buff163-scraper"
}

variable "dashboard_ecr_repo_name" {
  description = "ECR repository holding the Streamlit dashboard container image."
  type        = string
  default     = "buff163-dashboard"
}

variable "image_tag" {
  description = "Scraper Lambda container image tag to deploy (e.g. a git SHA or 'latest')."
  type        = string
  default     = "latest"
}

variable "dashboard_image_tag" {
  description = "Streamlit dashboard container image tag to deploy."
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

variable "vpc_cidr" {
  description = "CIDR block for the production VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Two public subnet CIDRs for NAT and public AWS entry points."
  type        = list(string)
  default     = ["10.42.0.0/24", "10.42.1.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Two private subnet CIDRs for Lambda, App Runner VPC connector, and RDS."
  type        = list(string)
  default     = ["10.42.10.0/24", "10.42.11.0/24"]
}

variable "db_name" {
  description = "Initial PostgreSQL database name."
  type        = string
  default     = "buff163"
}

variable "db_username" {
  description = "RDS master username. Password is managed by RDS in Secrets Manager."
  type        = string
  default     = "buff163_admin"
}

variable "db_instance_class" {
  description = "RDS PostgreSQL instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  description = "RDS allocated storage in GB."
  type        = number
  default     = 20
}

variable "db_backup_retention_days" {
  description = "RDS automated backup retention in days."
  type        = number
  default     = 7
}

variable "db_deletion_protection" {
  description = "Protect the RDS instance from accidental deletion."
  type        = bool
  default     = true
}

variable "db_skip_final_snapshot" {
  description = "Skip final RDS snapshot on destroy. Keep false for production."
  type        = bool
  default     = false
}

variable "dashboard_service_name" {
  description = "AWS App Runner service name for the Streamlit dashboard."
  type        = string
  default     = "buff163-dashboard"
}

variable "dashboard_cpu" {
  description = "App Runner dashboard CPU."
  type        = string
  default     = "0.25 vCPU"
}

variable "dashboard_memory" {
  description = "App Runner dashboard memory."
  type        = string
  default     = "0.5 GB"
}

variable "dashboard_env" {
  description = "Non-secret dashboard environment variables."
  type        = map(string)
  default = {
    STORAGE_BACKEND            = "postgres"
    BUFF_APP_LIVE_LISTINGS     = "0"
    BUFF_AUTO_MIGRATE_POSTGRES = "1"
  }
}

# Secret ARNs (created/managed OUTSIDE this stack so values never enter
# Terraform state). Lambda/App Runner are granted GetSecretValue on these plus
# the placeholder secrets created by this stack.
variable "secret_arns" {
  description = "ARNs of Secrets Manager secrets the Lambda may read (DATABASE_URL, BUFF_COOKIE, optional Google creds)."
  type        = list(string)
  default     = []
}

# Names of the secrets, passed to the Lambda as *_SECRET_ARN-style env so the
# app can fetch them at runtime. No secret VALUES are set here.
variable "database_url_secret_arn" {
  description = "Optional external Secrets Manager ARN for the Postgres DATABASE_URL. If empty, this stack creates a placeholder secret."
  type        = string
  default     = ""
}

variable "buff_cookie_secret_arn" {
  description = "Optional external Secrets Manager ARN for the BUFF163 cookie. If empty, this stack creates a placeholder secret."
  type        = string
  default     = ""
}

variable "extra_env" {
  description = "Additional non-secret environment variables for the Lambda."
  type        = map(string)
  default = {
    STORAGE_BACKEND            = "postgres"
    BUFF_AUTO_MIGRATE_POSTGRES = "1"
    BUFF_REQUEST_TIMEOUT       = "15"
    BUFF_MAX_RETRIES           = "3"
    BUFF_BACKOFF_BASE_SECONDS  = "1"
  }
}
