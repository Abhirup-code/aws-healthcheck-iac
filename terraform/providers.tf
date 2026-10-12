locals {
  endpoint = var.use_localstack ? var.localstack_endpoint : null
}

provider "aws" {
  region = var.aws_region

  # Fake credentials and skipped account checks, only for LocalStack and offline plans.
  access_key                  = var.use_localstack ? "test" : null
  secret_key                  = var.use_localstack ? "test" : null
  skip_credentials_validation = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  skip_requesting_account_id  = var.use_localstack
  s3_use_path_style           = var.use_localstack

  endpoints {
    s3               = local.endpoint
    sns              = local.endpoint
    iam              = local.endpoint
    sts              = local.endpoint
    lambda           = local.endpoint
    cloudwatch       = local.endpoint
    cloudwatchlogs   = local.endpoint
    cloudwatchevents = local.endpoint
  }
}
