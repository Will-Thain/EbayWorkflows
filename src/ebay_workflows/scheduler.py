"""Headless scheduler entrypoint (GUI-6). Dispatches due rows from scheduled_jobs."""

from __future__ import annotations

import sys

from .config import Settings
from .db import build_session_factory
from .scheduler_service import fetch_due_schedules, try_dispatch_one_due


def run_due_schedules() -> int:
    settings = Settings()
    session_factory = build_session_factory(settings)
    dispatched = 0
    with session_factory() as session:
        due_count = len(fetch_due_schedules(session, limit=50))
        if due_count == 0:
            return 0
        while True:
            job = try_dispatch_one_due(session, use_gui_runner=None, log_dir=settings.workflow_log_dir)
            if job is None:
                break
            dispatched += 1
            print(f"Dispatched schedule {job.name!r} ({job.job_id})", file=sys.stderr)
    return dispatched


def run_due_schedules_main() -> None:
    raise SystemExit(run_due_schedules())
