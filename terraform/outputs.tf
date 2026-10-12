output "report_bucket" {
  value = aws_s3_bucket.reports.bucket
}

output "alert_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "lambda_name" {
  value = aws_lambda_function.checker.function_name
}

output "alarm_name" {
  value = aws_cloudwatch_metric_alarm.failed_checks.alarm_name
}
