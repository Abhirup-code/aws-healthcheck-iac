"""AWS Lambda entry point.

Runs the checks, publishes a FailedChecks metric to CloudWatch, and saves a JSON
report to S3. The CloudWatch alarm (see terraform/main.tf) sends the alert to SNS.
Clients are passed in so tests can use fakes instead of boto3.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

try:  # package import (tests)
    from .checker import parse_targets, run_checks, summarize
except ImportError:  # flat import (Lambda zip has the files at the top level)
    from checker import parse_targets, run_checks, summarize  # type: ignore


def _boto_client(name: str):
    import boto3  # imported here so local tests do not need boto3

    return boto3.client(name, endpoint_url=os.environ.get("AWS_ENDPOINT_URL") or None)


def handler(event, context, cloudwatch=None, s3=None, now=None):
    targets = parse_targets(os.environ["TARGETS"])
    namespace = os.environ.get("METRIC_NAMESPACE", "CloudIacMonitoring")
    bucket = os.environ["REPORT_BUCKET"]

    results = run_checks(targets)
    summary = summarize(results)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H-%M-%SZ")

    cloudwatch = cloudwatch or _boto_client("cloudwatch")
    s3 = s3 or _boto_client("s3")

    cloudwatch.put_metric_data(
        Namespace=namespace,
        MetricData=[
            {"MetricName": "FailedChecks", "Value": summary["failed"], "Unit": "Count"},
            {"MetricName": "TotalChecks", "Value": summary["total"], "Unit": "Count"},
        ],
    )
    s3.put_object(
        Bucket=bucket,
        Key=f"reports/{stamp}.json",
        Body=json.dumps(summary, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    return {"failed": summary["failed"], "total": summary["total"]}
