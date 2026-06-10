from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ebay_workflows.models import Base, WorkflowRun, WorkflowStep
from ebay_workflows.operations.stale_workflows import (
    classify_step_lifecycle,
    clear_stale_workflow_steps,
    list_running_workflow_views,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _running_step(*, metrics: dict | None = None, minutes_ago: int = 60) -> WorkflowStep:
    session = _session()
    run = WorkflowRun(workflow_name="test", status="running")
    session.add(run)
    session.flush()
    started = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    step = WorkflowStep(
        run_id=run.id,
        step_name="phase5_ocr_verification",
        phase_number=5,
        status="running",
        started_at=started,
        metrics_json=metrics,
    )
    session.add(step)
    session.commit()
    session.refresh(step)
    return step


def test_classify_stale_without_progress() -> None:
    step = _running_step(minutes_ago=45)
    lifecycle, reason = classify_step_lifecycle(
        step=step,
        job_id="phase5",
        local_job_id=None,
        runner_busy=False,
        lock_pid=None,
        never_progress_minutes=10,
        stale_progress_minutes=30,
    )
    assert lifecycle == "stale"
    assert "No progress" in reason


def test_classify_live_with_recent_progress() -> None:
    now = datetime.now(timezone.utc).isoformat()
    step = _running_step(
        minutes_ago=120,
        metrics={"progress_current": 10, "progress_total": 100, "progress_updated_at": now},
    )
    lifecycle, _ = classify_step_lifecycle(
        step=step,
        job_id="phase5",
        local_job_id=None,
        runner_busy=False,
        lock_pid=None,
    )
    assert lifecycle == "live"


def test_clear_stale_marks_failed() -> None:
    session = _session()
    run = WorkflowRun(workflow_name="test", status="running")
    session.add(run)
    session.flush()
    started = datetime.now(timezone.utc) - timedelta(hours=2)
    step = WorkflowStep(
        run_id=run.id,
        step_name="phase2_title_match",
        phase_number=2,
        status="running",
        started_at=started,
    )
    session.add(step)
    session.commit()

    result = clear_stale_workflow_steps(
        session,
        [step.id],
        lock_path="/nonexistent/lock",
    )
    assert result.cleared_steps == 1
    session.refresh(step)
    session.refresh(run)
    assert step.status == "failed"
    assert step.error_json.get("cleared_stale") is True
    assert run.status == "failed"


def test_list_running_workflow_views_includes_warming() -> None:
    session = _session()
    run = WorkflowRun(workflow_name="test", status="running")
    session.add(run)
    session.flush()
    step = WorkflowStep(
        run_id=run.id,
        step_name="phase4_ev_ranking",
        phase_number=4,
        status="running",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    session.add(step)
    session.commit()

    views = list_running_workflow_views(
        session,
        local_job_id=None,
        runner_busy=False,
        lock_path="/nonexistent/lock",
    )
    assert len(views) == 1
    assert views[0].lifecycle == "warming"
    assert views[0].job_id == "phase4"
