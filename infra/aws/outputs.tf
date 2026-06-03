output "ecr_repository_url" {
  description = "Push the Lambda image here."
  value       = aws_ecr_repository.scraper.repository_url
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
