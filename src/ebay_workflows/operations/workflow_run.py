"""Shared workflow run / step bootstrap for phase executors."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models import WorkflowRun, WorkflowStep


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def begin_phase_run(
    session: Session,
    *,
    workflow_default_name: str,
    phase_number: int,
    step_name: str,
    input_config: dict[str, Any],
) -> tuple[WorkflowRun, WorkflowStep]:
    """Create a running workflow run and step row; caller commits on success."""
    run = WorkflowRun(
        workflow_name=f"{workflow_default_name}_phase{phase_number}",
        status="running",
        input_config_json=input_config,
        started_at=utc_now(),
    )
    session.add(run)
    session.flush()

    step = WorkflowStep(
        run_id=run.id,
        step_name=step_name,
        phase_number=phase_number,
        status="running",
        attempt=1,
        started_at=utc_now(),
    )
    session.add(step)
    session.flush()
    return run, step
