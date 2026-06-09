output "ecr_repository_url" {
  description = "Push the Lambda image here."
  value       = aws_ecr_repository.scraper.repository_url
}

output "dashboard_ecr_repository_url" {
  description = "Push the Streamlit dashboard image here."
  value       = aws_ecr_repository.dashboard.repository_url
}

output "lambda_function_name" {
  value = aws_lambda_function.scraper.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.scraper.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.lambda.name
}

output "schedule_name" {
  value = aws_scheduler_schedule.scraper.name
}

output "rds_endpoint" {
  description = "Private RDS PostgreSQL endpoint."
  value       = aws_db_instance.postgres.address
}

output "rds_port" {
  value = aws_db_instance.postgres.port
}

output "rds_database_name" {
  value = var.db_name
}

output "rds_master_secret_arn" {
  description = "RDS-managed Secrets Manager ARN containing master username/password JSON."
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
  sensitive   = true
}

output "database_url_secret_arn" {
  description = "Secret ARN where the app expects the final DATABASE_URL string."
  value       = local.database_url_secret_arn
}

output "buff_cookie_secret_arn" {
  description = "Secret ARN where the optional BUFF_COOKIE value belongs."
  value       = local.buff_cookie_secret_arn
}

output "dashboard_service_url" {
  description = "App Runner dashboard URL."
  value       = aws_apprunner_service.dashboard.service_url
}
