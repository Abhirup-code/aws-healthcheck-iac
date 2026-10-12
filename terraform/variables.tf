variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "iacmon"
}

variable "targets" {
  description = "URLs to check. expected_status and max_latency_ms are optional."
  type = list(object({
    name            = string
    url             = string
    expected_status = optional(number, 200)
    max_latency_ms  = optional(number, 2000)
  }))
  default = [
    { name = "example", url = "https://example.com" },
  ]
}

variable "alert_email" {
  description = "Email for alerts. Leave empty to skip the subscription."
  type        = string
  default     = ""
}

variable "schedule_expression" {
  description = "How often the checker runs."
  type        = string
  default     = "rate(5 minutes)"
}

variable "use_localstack" {
  description = "Point the AWS provider at LocalStack with fake credentials (no real AWS needed)."
  type        = bool
  default     = false
}

variable "localstack_endpoint" {
  description = "LocalStack edge URL, used only when use_localstack is true."
  type        = string
  default     = "http://localhost:4566"
}
