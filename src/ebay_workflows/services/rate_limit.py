from __future__ import annotations

import threading
import time


class GlobalRateLimiter:
    """Thread-safe minimum interval between outbound HTTP calls (CDN / art downloads)."""

    def __init__(self, requests_per_minute: int) -> None:
        self._interval = 60.0 / max(requests_per_minute, 1)
        self._lock = threading.Lock()
        self._next_allowed_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed_at:
                time.sleep(self._next_allowed_at - now)
            self._next_allowed_at = time.monotonic() + self._interval


_limiter: GlobalRateLimiter | None = None
_limiter_rpm: int | None = None


def get_global_rate_limiter(requests_per_minute: int) -> GlobalRateLimiter:
    global _limiter, _limiter_rpm
    if _limiter is None or _limiter_rpm != requests_per_minute:
        _limiter = GlobalRateLimiter(requests_per_minute)
        _limiter_rpm = requests_per_minute
    return _limiter


def wait_global_http(requests_per_minute: int) -> None:
    """Block until the shared outbound HTTP budget allows the next request."""
    get_global_rate_limiter(requests_per_minute).wait()
