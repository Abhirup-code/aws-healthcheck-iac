# aws-healthcheck-iac

[![CI](https://github.com/Abhirup-code/aws-healthcheck-iac/actions/workflows/ci.yml/badge.svg)](https://github.com/Abhirup-code/aws-healthcheck-iac/actions/workflows/ci.yml)

A small monitoring stack written as Terraform. A scheduled AWS Lambda checks a list of URLs, saves a JSON report to S3, and publishes a metric. A CloudWatch alarm on that metric sends an alert through SNS.

You can run and test all of it **without an AWS account**: unit tests, Terraform validate and plan, a security scan, and an optional local deploy with LocalStack.

> **Honest scope.** This project has not been deployed to a real AWS account. It is checked with unit tests, `terraform validate`, `terraform plan` (fake credentials), Checkov, and optionally LocalStack.

<img width="801" height="362" alt="Screenshot 2026-10-12 at 11 56 04 AM" src="https://github.com/user-attachments/assets/e6f8207a-212a-472d-92e1-d5a533ee7a5f" />

## How it works

```
EventBridge (every 5 min) -> Lambda health checker -> S3 (JSON report)
                                     |
                                     +-> CloudWatch metric FailedChecks
                                                  |
                                       CloudWatch alarm -> SNS topic -> email
```

- Each URL passes if the status code matches and the response is fast enough.
- The Lambda publishes `FailedChecks` on every run, even when it is 0.
- The alarm treats **missing data as breaching**, so if the Lambda stops running you also get an alert.
- The IAM role is least privilege: logs, `s3:PutObject` on one prefix, and `cloudwatch:PutMetricData` for one namespace.

## Layout

```
healthcheck/   checker.py (logic), lambda_handler.py (AWS entry point)
terraform/     S3, SNS, IAM, Lambda, EventBridge, CloudWatch alarm
tests/         31 tests (checker, handler, Terraform files)
.checkov.yaml  security scan settings
```

## Run the tests

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
```

The tests use fake clients and a small local web server, so they need no internet and no AWS.

## Check the Terraform (no AWS account)

Needs [Terraform](https://developer.hashicorp.com/terraform/install) 1.5 or newer.

```
cd terraform
terraform fmt -check
terraform init -backend=false
terraform validate
terraform plan -var use_localstack=true
```

`use_localstack=true` switches the provider to fake credentials and skips account lookups, so `plan` works offline.

## Deploy locally with LocalStack (optional, free)

Needs Docker.

```
docker compose up -d
cd terraform
terraform init
terraform apply -var use_localstack=true -auto-approve
terraform output
```

Stop it with `terraform destroy -var use_localstack=true -auto-approve` and `docker compose down`.

## Security scan

```
pip install checkov
checkov --config-file .checkov.yaml
```

49 checks pass. I skipped 13 checks on purpose for a small demo stack. Each skip has a one-line reason in `.checkov.yaml` (for example, no VPC because the Lambda must reach public URLs, and no KMS keys to avoid extra cost).

## Settings

| Variable | Default | What it does |
|---|---|---|
| `targets` | `example.com` | URLs to check, with optional `expected_status` and `max_latency_ms` |
| `alert_email` | empty | Adds an email subscription to the SNS topic |
| `schedule_expression` | `rate(5 minutes)` | How often the checker runs |
| `use_localstack` | `false` | Use LocalStack and fake credentials |
