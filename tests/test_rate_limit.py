from __future__ import annotations

import time

from ebay_workflows.operations.rate_limit import GlobalRateLimiter, get_global_rate_limiter


def test_global_rate_limiter_enforces_interval() -> None:
    limiter = GlobalRateLimiter(requests_per_minute=6000)
    start = time.monotonic()
    limiter.wait()
    limiter.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.01


def test_get_global_rate_limiter_reuses_instance_for_same_rpm() -> None:
    first = get_global_rate_limiter(120)
    second = get_global_rate_limiter(120)
    assert first is second
