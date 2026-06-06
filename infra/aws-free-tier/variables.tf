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
  description = "Lambda timeout in seconds."
  type        = number
  default     = 120
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
