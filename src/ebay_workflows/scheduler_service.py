from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .gui.workflow_catalog import WORKFLOW_JOBS
from .models import ScheduledJob, WorkflowStep
from .operations.detached_jobs import spawn_cli_job_detached


def workflow_is_running(session: Session) -> bool:
    count = session.scalar(
        select(func.count()).select_from(WorkflowStep).where(WorkflowStep.status == "running")
    )
    return int(count or 0) > 0


def compute_next_run_at(job: ScheduledJob, *, after: datetime | None = None) -> datetime | None:
    """Return the next UTC run time after `after` (default: now)."""
    after = after or datetime.now(timezone.utc)
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)

    if job.schedule_type == "interval":
        if job.interval_hours is None:
            return None
        hours = float(job.interval_hours)
        if hours < 1:
            hours = 1.0
        return after + timedelta(hours=hours)

    if job.schedule_type == "daily":
        if job.daily_at is None:
            return None
        try:
            tz = ZoneInfo(job.timezone or "UTC")
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("UTC")
        local_now = after.astimezone(tz)
        candidate = datetime.combine(local_now.date(), job.daily_at, tzinfo=tz)
        if candidate <= local_now:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)

    if job.schedule_type == "once":
        if job.run_at is None:
            return None
        run_at = job.run_at
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        return run_at if run_at > after else None

    return None


def refresh_next_run_at(session: Session, job: ScheduledJob, *, after: datetime | None = None) -> None:
    job.next_run_at = compute_next_run_at(job, after=after)
    if job.schedule_type == "once" and job.next_run_at is None:
        job.enabled = False
    job.updated_at = datetime.now(timezone.utc)
    session.commit()


def fetch_due_schedules(session: Session, *, limit: int = 10) -> list[ScheduledJob]:
    now = datetime.now(timezone.utc)
    return list(
        session.execute(
            select(ScheduledJob)
            .where(
                ScheduledJob.enabled.is_(True),
                ScheduledJob.next_run_at.is_not(None),
                ScheduledJob.next_run_at <= now,
            )
            .order_by(ScheduledJob.next_run_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def record_schedule_dispatch(session: Session, job: ScheduledJob, *, status: str = "dispatched") -> None:
    now = datetime.now(timezone.utc)
    job.last_run_at = now
    job.last_run_status = status
    job.last_error = None
    refresh_next_run_at(session, job, after=now)


def try_dispatch_one_due(
    session: Session,
    *,
    use_gui_runner: Any | None = None,
    log_dir: str | Path | None = None,
) -> ScheduledJob | None:
    """Dispatch at most one due schedule. Returns the row dispatched, if any."""
    if workflow_is_running(session):
        return None
    if use_gui_runner is not None and use_gui_runner.is_busy():
        return None

    due = fetch_due_schedules(session, limit=1)
    if not due:
        return None

    job = due[0]
    params = dict(job.job_params_json or {})
    if use_gui_runner is not None:
        use_gui_runner.start(job.job_id, params)
    else:
        spawn_cli_job_detached(job.job_id, params, log_dir=log_dir)
    record_schedule_dispatch(session, job)
    return job


def create_scheduled_job(
    session: Session,
    *,
    name: str,
    job_id: str,
    job_params_json: dict[str, Any],
    schedule_type: str,
    interval_hours: float | None = None,
    daily_at: time | None = None,
    run_at: datetime | None = None,
    timezone_name: str = "UTC",
    enabled: bool = True,
    catch_up_missed: bool = False,
) -> ScheduledJob:
    if job_id not in WORKFLOW_JOBS:
        raise ValueError(f"Unknown job_id: {job_id}")
    if schedule_type not in ("interval", "daily", "once"):
        raise ValueError(f"Invalid schedule_type: {schedule_type}")

    now = datetime.now(timezone.utc)
    row = ScheduledJob(
        name=name.strip(),
        job_id=job_id,
        job_params_json=job_params_json,
        schedule_type=schedule_type,
        interval_hours=interval_hours,
        daily_at=daily_at,
        run_at=run_at,
        timezone=timezone_name,
        enabled=enabled,
        catch_up_missed=catch_up_missed,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    refresh_next_run_at(session, row)
    return row
