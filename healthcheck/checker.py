"""Core health-check logic. Standard library only, so it runs anywhere."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Callable, Iterable, Optional


@dataclass
class Target:
    name: str
    url: str
    expected_status: int = 200
    max_latency_ms: int = 2000


@dataclass
class CheckResult:
    name: str
    url: str
    ok: bool
    status_code: Optional[int]
    latency_ms: Optional[int]
    error: Optional[str]


def parse_targets(raw: str) -> list[Target]:
    """Parse a JSON list of targets. Raises ValueError on bad input."""
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"targets is not valid JSON: {exc}") from exc
    if not isinstance(items, list) or not items:
        raise ValueError("targets must be a non-empty JSON list")
    targets = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or "name" not in item or "url" not in item:
            raise ValueError(f"target {i} needs 'name' and 'url'")
        if not str(item["url"]).startswith(("http://", "https://")):
            raise ValueError(f"target {item['name']!r} url must start with http:// or https://")
        targets.append(
            Target(
                name=str(item["name"]),
                url=str(item["url"]),
                expected_status=int(item.get("expected_status", 200)),
                max_latency_ms=int(item.get("max_latency_ms", 2000)),
            )
        )
    return targets


def check_target(
    target: Target,
    timeout: float = 5.0,
    opener: Callable = urllib.request.urlopen,
    clock: Callable[[], float] = time.monotonic,
) -> CheckResult:
    """Check one URL. A target passes if the status matches and it is fast enough."""
    start = clock()
    status: Optional[int] = None
    error: Optional[str] = None
    try:
        with opener(target.url, timeout=timeout) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        error = f"{type(exc).__name__}: {getattr(exc, 'reason', exc)}"
    latency = int((clock() - start) * 1000)

    ok = error is None and status == target.expected_status
    if error is None and status != target.expected_status:
        error = f"expected status {target.expected_status}, got {status}"
    elif ok and latency > target.max_latency_ms:
        ok = False
        error = f"too slow: {latency} ms (limit {target.max_latency_ms} ms)"
    return CheckResult(target.name, target.url, ok, status, latency, error)


def run_checks(targets: Iterable[Target], **kwargs) -> list[CheckResult]:
    return [check_target(t, **kwargs) for t in targets]


def summarize(results: list[CheckResult]) -> dict:
    failed = [r for r in results if not r.ok]
    return {
        "total": len(results),
        "failed": len(failed),
        "passed": len(results) - len(failed),
        "results": [asdict(r) for r in results],
    }


def build_alert_text(results: list[CheckResult]) -> Optional[str]:
    """Plain-text alert body, or None when everything passed."""
    failed = [r for r in results if not r.ok]
    if not failed:
        return None
    lines = [f"{len(failed)} of {len(results)} health checks failed:"]
    for r in failed:
        lines.append(f"- {r.name} ({r.url}): {r.error}")
    return "\n".join(lines)
