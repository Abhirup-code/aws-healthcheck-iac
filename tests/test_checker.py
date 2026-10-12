import json
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from healthcheck.checker import (
    Target,
    build_alert_text,
    check_target,
    parse_targets,
    run_checks,
    summarize,
)


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_returning(status):
    return lambda url, timeout: FakeResponse(status)


def ticking_clock(step):
    t = {"v": 0.0}

    def clock():
        t["v"] += step
        return t["v"]

    return clock


# ---- parse_targets ----
def test_parse_targets_defaults():
    t = parse_targets('[{"name": "a", "url": "https://a.test"}]')
    assert t == [Target("a", "https://a.test", 200, 2000)]


def test_parse_targets_custom_values():
    t = parse_targets('[{"name":"a","url":"http://a","expected_status":204,"max_latency_ms":50}]')
    assert t[0].expected_status == 204 and t[0].max_latency_ms == 50


@pytest.mark.parametrize(
    "raw",
    ["not json", "[]", "{}", '[{"name":"a"}]', '[{"name":"a","url":"ftp://x"}]', "[1]"],
)
def test_parse_targets_rejects_bad_input(raw):
    with pytest.raises(ValueError):
        parse_targets(raw)


# ---- check_target with fakes ----
def test_pass_on_expected_status():
    r = check_target(Target("a", "http://a"), opener=opener_returning(200), clock=ticking_clock(0.01))
    assert r.ok and r.status_code == 200 and r.error is None


def test_fail_on_wrong_status():
    r = check_target(Target("a", "http://a"), opener=opener_returning(503), clock=ticking_clock(0.01))
    assert not r.ok and r.status_code == 503 and "expected status 200" in r.error


def test_http_error_is_a_status_not_a_crash():
    def opener(url, timeout):
        raise urllib.error.HTTPError(url, 500, "boom", {}, None)

    r = check_target(Target("a", "http://a"), opener=opener, clock=ticking_clock(0.01))
    assert not r.ok and r.status_code == 500


def test_expected_non_200_status_passes():
    r = check_target(Target("a", "http://a", expected_status=404), opener=opener_returning(404), clock=ticking_clock(0.01))
    assert r.ok


def test_connection_error_reported():
    def opener(url, timeout):
        raise urllib.error.URLError("refused")

    r = check_target(Target("a", "http://a"), opener=opener, clock=ticking_clock(0.01))
    assert not r.ok and r.status_code is None and "refused" in r.error


def test_timeout_reported():
    def opener(url, timeout):
        raise TimeoutError("timed out")

    r = check_target(Target("a", "http://a"), opener=opener, clock=ticking_clock(0.01))
    assert not r.ok and "TimeoutError" in r.error


def test_slow_response_fails():
    r = check_target(
        Target("a", "http://a", max_latency_ms=100),
        opener=opener_returning(200),
        clock=ticking_clock(0.5),
    )
    assert not r.ok and "too slow" in r.error


def test_latency_exactly_at_limit_passes():
    r = check_target(
        Target("a", "http://a", max_latency_ms=500),
        opener=opener_returning(200),
        clock=ticking_clock(0.5),
    )
    assert r.ok and r.latency_ms == 500


# ---- summarize / alert ----
def _mixed():
    ok = opener_returning(200)
    bad = opener_returning(500)
    return [
        check_target(Target("good", "http://g"), opener=ok, clock=ticking_clock(0.001)),
        check_target(Target("bad", "http://b"), opener=bad, clock=ticking_clock(0.001)),
    ]


def test_summarize_counts():
    s = summarize(_mixed())
    assert (s["total"], s["passed"], s["failed"]) == (2, 1, 1)
    assert s["results"][1]["name"] == "bad"
    json.dumps(s)  # must be JSON serializable


def test_alert_text_lists_only_failures():
    text = build_alert_text(_mixed())
    assert "1 of 2" in text and "bad" in text and "good" not in text


def test_alert_text_none_when_all_pass():
    ok = [check_target(Target("g", "http://g"), opener=opener_returning(200), clock=ticking_clock(0.001))]
    assert build_alert_text(ok) is None


# ---- real local HTTP server (no internet needed) ----
class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok":
            self.send_response(200)
        elif self.path == "/slow":
            time.sleep(0.3)
            self.send_response(200)
        else:
            self.send_response(500)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_real_server_ok_and_500(server):
    results = run_checks([Target("ok", server + "/ok"), Target("err", server + "/err")])
    assert [r.ok for r in results] == [True, False]
    assert results[1].status_code == 500


def test_real_server_slow(server):
    r = check_target(Target("slow", server + "/slow", max_latency_ms=50))
    assert not r.ok and "too slow" in r.error


def test_real_server_down():
    # port 1 is not listening
    r = check_target(Target("down", "http://127.0.0.1:1/"), timeout=1)
    assert not r.ok and r.status_code is None
