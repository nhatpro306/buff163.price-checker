output "cloudfront_url" {
  description = "HTTPS static dashboard URL."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "bucket_name" {
  description = "Private S3 bucket storing index.html and data.json."
  value       = aws_s3_bucket.site.bucket
}

output "lambda_function_name" {
  description = "Scheduled static-site scraper Lambda."
  value       = aws_lambda_function.scraper.function_name
}

output "schedule_name" {
  description = "EventBridge Scheduler rule."
  value       = aws_scheduler_schedule.scraper.name
}

output "log_group_name" {
  description = "Lambda CloudWatch log group."
  value       = aws_cloudwatch_log_group.scraper.name
}
