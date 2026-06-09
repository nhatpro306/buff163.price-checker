variable "aws_region" {
  description = "AWS region for the scheduled scraper Lambda."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Name prefix for free-tier resources."
  type        = string
  default     = "buff163-free"
}

variable "schedule_expression" {
  description = "EventBridge schedule for static site refreshes."
  type        = string
  default     = "rate(1 day)"
}

variable "lambda_memory_mb" {
  description = "Lambda memory. Keep small to stay within Lambda free tier."
  type        = number
  default     = 256
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds. Needs headroom for optional BUFF listing + price-history fetch (rate-limited)."
  type        = number
  default     = 300
}

variable "log_retention_days" {
  description = "CloudWatch log retention."
  type        = number
  default     = 7
}

variable "track_keywords" {
  description = "Comma-separated market keywords to publish."
  type        = string
  default     = "Bayonet,Bowie Knife,Butterfly Knife,Classic Knife,Falchion Knife,Flip Knife,Gut Knife,Huntsman Knife,Karambit,Kukri Knife,M9 Bayonet,Navaja Knife,Nomad Knife,Paracord Knife,Shadow Daggers,Skeleton Knife,Stiletto Knife,Survival Knife,Talon Knife,Ursus Knife"
}

variable "budget_alert_email" {
  description = "Optional email address for a low monthly AWS Budget alert. Leave empty to skip budget creation."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD when budget_alert_email is set."
  type        = string
  default     = "1.00"
}

variable "lambda_reserved_concurrency" {
  description = "Reserved concurrency cap. Set to a positive number to harden against fan-out. Default -1 = unreserved (required on accounts with the default 10-concurrency quota where reserving any value would drop UnreservedConcurrentExecutions below the AWS minimum of 10)."
  type        = number
  default     = -1
}

variable "log_level" {
  description = "Python logging level for the Lambda."
  type        = string
  default     = "INFO"
}

variable "request_timeout_seconds" {
  description = "HTTP request timeout for upstream scrape calls."
  type        = number
  default     = 15
}

variable "max_retries" {
  description = "Retry attempts on upstream scrape failure."
  type        = number
  default     = 3
}

variable "raw_keep_days" {
  description = "Days to keep raw/ S3 backups before lifecycle deletion."
  type        = number
  default     = 14
}

variable "history_keep_days" {
  description = "Days to keep history/ S3 snapshots before lifecycle deletion."
  type        = number
  default     = 90
}

variable "write_sheets" {
  description = "Set true to also write Google Sheets from Lambda. Requires spreadsheet_id, worksheet_name, and google_creds_ssm_param."
  type        = bool
  default     = false
}

variable "spreadsheet_id" {
  description = "Google Sheets spreadsheet ID (only when write_sheets=true)."
  type        = string
  default     = ""
}

variable "worksheet_name" {
  description = "Target worksheet name (only when write_sheets=true)."
  type        = string
  default     = ""
}

variable "google_creds_ssm_param" {
  description = "SSM Parameter Store path holding service-account JSON. Create manually as SecureString."
  type        = string
  default     = "/buff163/google-creds"
}

variable "discord_webhook_ssm_param" {
  description = "SSM Parameter Store path holding the Discord webhook URL. Create manually as SecureString. Leave empty to skip Discord alerts."
  type        = string
  default     = ""
}

variable "buff_cookie_ssm_param" {
  description = "SSM Parameter Store path holding a BUFF163 session cookie (SecureString). When set and populated, the Lambda enriches the most-listed knives with real Sell(N) listing counts. Leave default and simply do not create the parameter to stay price-only."
  type        = string
  default     = "/buff163/cookie"
}

variable "listing_pages" {
  description = "BUFF goods-list pages (50/page, sorted by sell_num desc) to fetch for listing enrichment. 4 pages ~= top 200 most-listed knives."
  type        = number
  default     = 4
}
