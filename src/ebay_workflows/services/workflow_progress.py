from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import WorkflowStep
from .progress_report import ProgressSnapshot


def publish_step_progress(
    session: Session,
    step: WorkflowStep,
    current: int,
    total: int,
    *,
    unit: str = "items",
) -> None:
    """Persist progress on the running step so the GUI can monitor external CLI processes."""
    payload: dict[str, Any] = dict(step.metrics_json or {})
    payload["progress_current"] = current
    payload["progress_total"] = total
    payload["progress_unit"] = unit
    step.metrics_json = payload
    session.commit()


def progress_from_step_metrics(step: WorkflowStep) -> ProgressSnapshot | None:
    metrics = step.metrics_json or {}
    total = metrics.get("progress_total")
    current = metrics.get("progress_current")
    if total is None or current is None:
        return None
    try:
        total_i = int(total)
        current_i = int(current)
    except (TypeError, ValueError):
        return None
    if total_i <= 0:
        return None
    unit = str(metrics.get("progress_unit") or "items")
    return ProgressSnapshot(current=current_i, total=total_i, unit=unit)
