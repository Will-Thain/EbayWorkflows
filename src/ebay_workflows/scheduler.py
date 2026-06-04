"""Headless scheduler entrypoint (GUI-6). Dispatches due rows from scheduled_jobs."""

from __future__ import annotations

import sys

from sqlalchemy import select

from .config import Settings
from .db import build_session_factory
from .models import ScheduledJob


def run_due_schedules() -> int:
    settings = Settings()
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        due = (
            session.execute(
                select(ScheduledJob).where(
                    ScheduledJob.enabled.is_(True),
                    ScheduledJob.next_run_at.is_not(None),
                )
            )
            .scalars()
            .all()
        )
        if not due:
            return 0
        print(
            "Scheduled jobs exist but dispatch is not implemented yet (GUI-6).",
            file=sys.stderr,
        )
        return 0


def run_due_schedules_main() -> None:
    raise SystemExit(run_due_schedules())
