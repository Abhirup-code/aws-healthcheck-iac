# Small monitoring stack: a scheduled Lambda checks URLs, writes a report to S3,
# and publishes a metric. A CloudWatch alarm on that metric notifies an SNS topic.

# ---------- Report storage ----------
resource "aws_s3_bucket" "reports" {
  bucket        = "${var.name_prefix}-reports"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "reports" {
  bucket                  = aws_s3_bucket.reports.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "reports" {
  bucket = aws_s3_bucket.reports.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    id     = "expire-old-reports"
    status = "Enabled"
    filter {
      prefix = "reports/"
    }
    expiration {
      days = 30
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# ---------- Alerts ----------
resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ---------- Lambda ----------
data "archive_file" "checker" {
  type        = "zip"
  source_dir  = "${path.module}/../healthcheck"
  output_path = "${path.module}/build/checker.zip"
  excludes    = ["__pycache__", "__init__.py"]
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "checker" {
  name               = "${var.name_prefix}-checker"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Least privilege: write logs, write reports to one bucket, publish metrics.
data "aws_iam_policy_document" "checker" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.checker.arn}:*"]
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.reports.arn}/reports/*"]
  }
  statement {
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = [local.metric_namespace]
    }
  }
}

resource "aws_iam_role_policy" "checker" {
  name   = "${var.name_prefix}-checker"
  role   = aws_iam_role.checker.id
  policy = data.aws_iam_policy_document.checker.json
}

locals {
  metric_namespace = "CloudIacMonitoring"
}

resource "aws_cloudwatch_log_group" "checker" {
  name              = "/aws/lambda/${var.name_prefix}-checker"
  retention_in_days = 14
}

resource "aws_lambda_function" "checker" {
  function_name    = "${var.name_prefix}-checker"
  role             = aws_iam_role.checker.arn
  runtime          = "python3.12"
  handler          = "lambda_handler.handler"
  filename         = data.archive_file.checker.output_path
  source_code_hash = data.archive_file.checker.output_base64sha256
  timeout          = 30
  memory_size      = 128

  environment {
    variables = {
      TARGETS          = jsonencode(var.targets)
      REPORT_BUCKET    = aws_s3_bucket.reports.bucket
      METRIC_NAMESPACE = local.metric_namespace
      AWS_ENDPOINT_URL = var.use_localstack ? "http://host.docker.internal:4566" : ""
    }
  }

  depends_on = [aws_cloudwatch_log_group.checker]
}

# ---------- Schedule ----------
resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${var.name_prefix}-schedule"
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "checker" {
  rule = aws_cloudwatch_event_rule.schedule.name
  arn  = aws_lambda_function.checker.arn
}

resource "aws_lambda_permission" "events" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.checker.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}

# ---------- Alarm ----------
# Missing data counts as breaching, so a Lambda that stops running also alerts.
resource "aws_cloudwatch_metric_alarm" "failed_checks" {
  alarm_name          = "${var.name_prefix}-failed-checks"
  alarm_description   = "One or more health checks failed, or the checker stopped reporting."
  namespace           = local.metric_namespace
  metric_name         = "FailedChecks"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}
