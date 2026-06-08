from __future__ import annotations

from datetime import datetime, time, timezone
from types import SimpleNamespace

from ebay_workflows.scheduler_service import compute_next_run_at


def _job(**fields):
    defaults = {
        "schedule_type": "interval",
        "interval_hours": 24,
        "daily_at": None,
        "run_at": None,
        "timezone": "UTC",
    }
    defaults.update(fields)
    return SimpleNamespace(**defaults)


def test_interval_next_run() -> None:
    after = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    job = _job(schedule_type="interval", interval_hours=2)
    nxt = compute_next_run_at(job, after=after)  # type: ignore[arg-type]
    assert nxt == datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)


def test_daily_next_run_same_day() -> None:
    after = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    job = _job(schedule_type="daily", daily_at=time(9, 0), timezone="UTC")
    nxt = compute_next_run_at(job, after=after)  # type: ignore[arg-type]
    assert nxt == datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)


def test_daily_next_run_rolls_to_tomorrow() -> None:
    after = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    job = _job(schedule_type="daily", daily_at=time(9, 0), timezone="UTC")
    nxt = compute_next_run_at(job, after=after)  # type: ignore[arg-type]
    assert nxt == datetime(2026, 6, 2, 9, 0, tzinfo=timezone.utc)


def test_once_future() -> None:
    after = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    run_at = datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc)
    job = _job(schedule_type="once", run_at=run_at)
    nxt = compute_next_run_at(job, after=after)  # type: ignore[arg-type]
    assert nxt == run_at


def test_once_past_returns_none() -> None:
    after = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    run_at = datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc)
    job = _job(schedule_type="once", run_at=run_at)
    assert compute_next_run_at(job, after=after) is None  # type: ignore[arg-type]
