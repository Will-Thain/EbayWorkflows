from __future__ import annotations

from datetime import datetime, time, timezone
from unittest.mock import MagicMock

from ebay_workflows.scheduler_service import (
    compute_next_run_at,
    try_dispatch_one_due,
    workflow_is_running,
)
from types import SimpleNamespace


def test_try_dispatch_skips_when_workflow_running() -> None:
    session = MagicMock()
    session.scalar.return_value = 1
    runner = MagicMock()
    runner.is_busy.return_value = False
    assert try_dispatch_one_due(session, use_gui_runner=runner) is None
    runner.start.assert_not_called()


def test_workflow_is_running_false_when_zero() -> None:
    session = MagicMock()
    session.scalar.return_value = 0
    assert workflow_is_running(session) is False


def test_compute_once_past_returns_none() -> None:
    job = SimpleNamespace(
        schedule_type="once",
        interval_hours=None,
        daily_at=None,
        run_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        timezone="UTC",
    )
    assert compute_next_run_at(job, after=datetime(2026, 1, 1, tzinfo=timezone.utc)) is None  # type: ignore[arg-type]


def test_compute_daily_timezone() -> None:
    job = SimpleNamespace(
        schedule_type="daily",
        interval_hours=None,
        daily_at=time(7, 30),
        run_at=None,
        timezone="Europe/London",
    )
    after = datetime(2026, 6, 4, 6, 0, tzinfo=timezone.utc)
    nxt = compute_next_run_at(job, after=after)  # type: ignore[arg-type]
    assert nxt is not None
    assert nxt > after
