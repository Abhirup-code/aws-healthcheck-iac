import json
from datetime import datetime, timezone

import pytest

from healthcheck import lambda_handler
from healthcheck.checker import CheckResult


class FakeCW:
    def __init__(self):
        self.calls = []

    def put_metric_data(self, **kw):
        self.calls.append(kw)


class FakeS3:
    def __init__(self):
        self.calls = []

    def put_object(self, **kw):
        self.calls.append(kw)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TARGETS", json.dumps([{"name": "a", "url": "http://a"}, {"name": "b", "url": "http://b"}]))
    monkeypatch.setenv("REPORT_BUCKET", "my-bucket")
    monkeypatch.setenv("METRIC_NAMESPACE", "TestNS")


def fake_results(failed):
    return lambda targets: [
        CheckResult(t.name, t.url, ok=(i >= failed), status_code=200, latency_ms=5, error=None if i >= failed else "boom")
        for i, t in enumerate(targets)
    ]


def run(monkeypatch, failed):
    monkeypatch.setattr(lambda_handler, "run_checks", fake_results(failed))
    cw, s3 = FakeCW(), FakeS3()
    out = lambda_handler.handler({}, None, cloudwatch=cw, s3=s3, now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    return out, cw, s3


def test_publishes_failed_count_metric(env, monkeypatch):
    out, cw, _ = run(monkeypatch, failed=1)
    assert out == {"failed": 1, "total": 2}
    call = cw.calls[0]
    assert call["Namespace"] == "TestNS"
    values = {m["MetricName"]: m["Value"] for m in call["MetricData"]}
    assert values == {"FailedChecks": 1, "TotalChecks": 2}


def test_zero_failures_still_publishes_metric(env, monkeypatch):
    # The alarm treats missing data as breaching, so a healthy run must still report 0.
    out, cw, _ = run(monkeypatch, failed=0)
    values = {m["MetricName"]: m["Value"] for m in cw.calls[0]["MetricData"]}
    assert values["FailedChecks"] == 0


def test_report_saved_to_s3(env, monkeypatch):
    _, _, s3 = run(monkeypatch, failed=2)
    put = s3.calls[0]
    assert put["Bucket"] == "my-bucket"
    assert put["Key"] == "reports/2026-01-02T03-04-05Z.json"
    body = json.loads(put["Body"])
    assert body["failed"] == 2 and len(body["results"]) == 2


def test_bad_targets_env_raises(monkeypatch):
    monkeypatch.setenv("TARGETS", "nope")
    monkeypatch.setenv("REPORT_BUCKET", "b")
    with pytest.raises(ValueError):
        lambda_handler.handler({}, None, cloudwatch=FakeCW(), s3=FakeS3())
