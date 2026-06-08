from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import WorkflowRun, WorkflowStep
from ..workflow_errors import build_operator_error_json
from ..workflow_steps import job_id_for_step
from .pipeline_lock import _pid_alive


def _elapsed_label(step: WorkflowStep) -> str:
    started = _ensure_utc(step.started_at)
    seconds = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


@dataclass(frozen=True, slots=True)
class RunningWorkflowView:
    step_id: uuid.UUID
    run_id: uuid.UUID
    job_id: str
    step_name: str
    phase_number: int
    started_at: datetime
    lifecycle: str  # live | warming | stale
    reason: str
    age_label: str

    @property
    def can_clear(self) -> bool:
        return self.lifecycle == "stale"


@dataclass(frozen=True, slots=True)
class ClearStaleResult:
    cleared_steps: int
    skipped_live: int


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_progress_updated(metrics: dict[str, Any]) -> datetime | None:
    raw = metrics.get("progress_updated_at")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return _ensure_utc(parsed)


def lock_holder_pid(lock_path: str | Path) -> int | None:
    path = Path(lock_path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        pid = int(payload.get("pid", 0))
    except (json.JSONDecodeError, ValueError, TypeError, OSError):
        return None
    return pid if _pid_alive(pid) else None


def classify_step_lifecycle(
    *,
    step: WorkflowStep,
    job_id: str,
    local_job_id: str | None,
    runner_busy: bool,
    lock_pid: int | None,
    never_progress_minutes: int = 10,
    stale_progress_minutes: int = 30,
) -> tuple[str, str]:
    if runner_busy and local_job_id == job_id:
        return "live", "Running in this GUI session"

    if lock_pid is not None and job_id == "phase1":
        return "live", f"Pipeline lock held (pid={lock_pid})"

    metrics = step.metrics_json or {}
    updated_at = _parse_progress_updated(metrics)
    started = _ensure_utc(step.started_at)
    now = datetime.now(timezone.utc)

    if updated_at is not None:
        age_since_progress = now - updated_at
        if age_since_progress <= timedelta(minutes=stale_progress_minutes):
            return "live", "Progress updating recently"
        minutes = max(1, int(age_since_progress.total_seconds() // 60))
        return "stale", f"No progress for {minutes} minutes"

    running_for = now - started
    if running_for <= timedelta(minutes=never_progress_minutes):
        return "warming", "Recently started; awaiting first progress report"
    minutes = max(1, int(running_for.total_seconds() // 60))
    return "stale", f"No progress reported for {minutes} minutes"


def list_running_workflow_views(
    session: Session,
    *,
    local_job_id: str | None,
    runner_busy: bool,
    lock_path: str | Path,
    never_progress_minutes: int = 10,
    stale_progress_minutes: int = 30,
) -> list[RunningWorkflowView]:
    lock_pid = lock_holder_pid(lock_path)
    rows = session.execute(
        select(WorkflowStep, WorkflowRun)
        .join(WorkflowRun, WorkflowRun.id == WorkflowStep.run_id)
        .where(WorkflowStep.status == "running")
        .order_by(WorkflowStep.started_at.desc())
    ).all()

    views: list[RunningWorkflowView] = []
    for step, run in rows:
        job_id = job_id_for_step(step.step_name)
        lifecycle, reason = classify_step_lifecycle(
            step=step,
            job_id=job_id,
            local_job_id=local_job_id,
            runner_busy=runner_busy,
            lock_pid=lock_pid,
            never_progress_minutes=never_progress_minutes,
            stale_progress_minutes=stale_progress_minutes,
        )
        views.append(
            RunningWorkflowView(
                step_id=step.id,
                run_id=run.id,
                job_id=job_id,
                step_name=step.step_name,
                phase_number=step.phase_number,
                started_at=_ensure_utc(step.started_at),
                lifecycle=lifecycle,
                reason=reason,
                age_label=_elapsed_label(step),
            )
        )
    return views


def clear_stale_workflow_steps(
    session: Session,
    step_ids: Iterable[uuid.UUID],
    *,
    reason: str = "Operator cleared hung/inactive workflow",
    only_if_stale: bool = True,
    local_job_id: str | None = None,
    runner_busy: bool = False,
    lock_path: str | Path = "",
) -> ClearStaleResult:
    """Mark running workflow steps failed so pipeline mutex can proceed."""
    requested = {uuid.UUID(str(step_id)) for step_id in step_ids}
    if not requested:
        return ClearStaleResult(cleared_steps=0, skipped_live=0)

    stale_ids: set[uuid.UUID] = set()
    skipped_live = 0
    if only_if_stale:
        for view in list_running_workflow_views(
            session,
            local_job_id=local_job_id,
            runner_busy=runner_busy,
            lock_path=lock_path or ".",
        ):
            if view.step_id in requested:
                if view.can_clear:
                    stale_ids.add(view.step_id)
                else:
                    skipped_live += 1
    else:
        stale_ids = requested

    now = datetime.now(timezone.utc)
    cleared = 0
    for step_id in stale_ids:
        step = session.get(WorkflowStep, step_id)
        if step is None or step.status != "running":
            continue
        run = session.get(WorkflowRun, step.run_id)
        step.status = "failed"
        step.finished_at = now
        step.error_json = build_operator_error_json(reason, cleared_stale=True)
        if run is not None and run.status == "running":
            run.status = "failed"
            run.finished_at = now
        cleared += 1

    if cleared:
        session.commit()
    return ClearStaleResult(cleared_steps=cleared, skipped_live=skipped_live)


def delete_workflow_steps(
    session: Session,
    step_ids: Iterable[uuid.UUID],
) -> int:
    """Remove workflow step rows (and orphan runs with no remaining steps)."""
    deleted = 0
    run_ids: set[uuid.UUID] = set()
    for step_id in step_ids:
        step = session.get(WorkflowStep, uuid.UUID(str(step_id)))
        if step is None:
            continue
        run_ids.add(step.run_id)
        session.delete(step)
        deleted += 1

    for run_id in run_ids:
        run = session.get(WorkflowRun, run_id)
        if run is None:
            continue
        remaining = session.scalar(
            select(WorkflowStep.id).where(WorkflowStep.run_id == run_id).limit(1)
        )
        if remaining is None:
            session.delete(run)
        elif run.status == "running":
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)

    if deleted:
        session.commit()
    return deleted
