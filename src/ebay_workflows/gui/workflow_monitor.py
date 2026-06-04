from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Listing, ListingFavorite, ListingImage, ListingScore, WorkflowRun, WorkflowStep
from ..services.progress_report import ProgressSnapshot
from ..services.workflow_progress import progress_from_step_metrics
from .progress_estimates import poll_job_progress

STEP_TO_JOB: dict[str, str] = {
    "phase1_ingest": "phase1",
    "phase2_title_match": "phase2",
    "phase3_cardmarket_join": "phase3",
    "phase4_ev_ranking": "phase4",
    "phase5_ocr_verification": "phase5",
    "phase6_bulk_lot_detection": "phase6",
}


@dataclass(frozen=True, slots=True)
class ActiveWorkflow:
    step: WorkflowStep
    run: WorkflowRun
    job_id: str
    source: str  # gui | external

    @property
    def step_label(self) -> str:
        return self.step.step_name


def job_id_for_step(step_name: str) -> str:
    return STEP_TO_JOB.get(step_name, step_name)


@dataclass(frozen=True, slots=True)
class DashboardStats:
    listing_count: int
    ranked_count: int
    favorite_count: int
    images_cached: int
    running_count: int


def fetch_dashboard_stats(session: Session) -> DashboardStats:
    listing_count = int(session.scalar(select(func.count()).select_from(Listing)) or 0)
    ranked_count = int(session.scalar(select(func.count()).select_from(ListingScore)) or 0)
    favorite_count = int(session.scalar(select(func.count()).select_from(ListingFavorite)) or 0)
    images_cached = int(
        session.scalar(
            select(func.count())
            .select_from(ListingImage)
            .where(ListingImage.download_status == "succeeded", ListingImage.local_path.is_not(None))
        )
        or 0
    )
    running_count = int(
        session.scalar(
            select(func.count()).select_from(WorkflowStep).where(WorkflowStep.status == "running")
        )
        or 0
    )
    return DashboardStats(
        listing_count=listing_count,
        ranked_count=ranked_count,
        favorite_count=favorite_count,
        images_cached=images_cached,
        running_count=running_count,
    )


def fetch_running_workflows(session: Session) -> list[ActiveWorkflow]:
    rows = session.execute(
        select(WorkflowStep, WorkflowRun)
        .join(WorkflowRun, WorkflowRun.id == WorkflowStep.run_id)
        .where(WorkflowStep.status == "running")
        .order_by(WorkflowStep.started_at.desc())
    ).all()
    return [
        ActiveWorkflow(
            step=step,
            run=run,
            job_id=job_id_for_step(step.step_name),
            source="external",
        )
        for step, run in rows
    ]


def fetch_active_workflow(session: Session) -> ActiveWorkflow | None:
    workflows = fetch_running_workflows(session)
    return workflows[0] if workflows else None


def workflow_source_label(active: ActiveWorkflow, local_job_id: str | None) -> str:
    if local_job_id and local_job_id == active.job_id:
        return "GUI"
    return "External"


def fetch_recent_steps(session: Session, *, limit: int = 10) -> tuple[list[str], list[tuple[Any, ...]]]:
    rows = session.execute(
        select(WorkflowStep, WorkflowRun)
        .join(WorkflowRun, WorkflowRun.id == WorkflowStep.run_id)
        .order_by(WorkflowStep.started_at.desc())
        .limit(limit)
    ).all()
    headers = ["Phase", "Step", "Status", "Started", "Duration", "Run"]
    table_rows: list[tuple[Any, ...]] = []
    for step, run in rows:
        duration = "—"
        if step.finished_at and step.started_at:
            started = step.started_at
            finished = step.finished_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=timezone.utc)
            seconds = max(0, int((finished - started).total_seconds()))
            duration = elapsed_label_from_seconds(seconds)
        elif step.status == "running":
            duration = elapsed_label(step)
        started_display = step.started_at.strftime("%Y-%m-%d %H:%M") if step.started_at else ""
        table_rows.append(
            (
                step.phase_number,
                step.step_name,
                step.status,
                started_display,
                duration,
                str(run.id)[:8],
            )
        )
    return headers, table_rows


def elapsed_label_from_seconds(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def resolve_progress(session: Session, active: ActiveWorkflow) -> ProgressSnapshot | None:
    from_metrics = progress_from_step_metrics(active.step)
    if from_metrics:
        return from_metrics
    polled = poll_job_progress(session, active.job_id)
    if polled:
        current, total, unit = polled
        return ProgressSnapshot(current=current, total=total, unit=unit)
    return None


def elapsed_label(step: WorkflowStep) -> str:
    started = step.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    seconds = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
    return elapsed_label_from_seconds(seconds)
