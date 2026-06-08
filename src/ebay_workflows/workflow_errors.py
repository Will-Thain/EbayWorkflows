from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from .models import WorkflowRun, WorkflowStep

logger = structlog.get_logger(__name__)


def error_category_for(exc: BaseException) -> str:
    if isinstance(exc, ValidationError):
        return "ConfigurationError"
    if isinstance(exc, ValueError):
        return "ConfigurationError"
    if isinstance(exc, OperationalError):
        return "TransientIntegrationError"
    if isinstance(exc, SQLAlchemyError):
        return "WorkflowExecutionError"
    name = type(exc).__name__
    if name in {"AuthenticationError", "AuthorizationError"}:
        return name
    if name in {"RateLimitError", "TransientIntegrationError"}:
        return name
    if name in {"PermanentIntegrationError", "DataValidationError", "DataSourceError"}:
        return name
    return "WorkflowExecutionError"


def build_step_error_json(
    step: WorkflowStep,
    run: WorkflowRun,
    exc: BaseException,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "category": error_category_for(exc),
        "message": str(exc) or type(exc).__name__,
        "exception_type": type(exc).__name__,
        "step_name": step.step_name,
        "run_id": str(run.id),
    }
    if extra:
        payload.update(extra)
    return payload


def build_operator_error_json(message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "category": "WorkflowExecutionError",
        "message": message,
    }
    if extra:
        payload.update(extra)
    return payload


def fail_workflow_step(
    session: Session,
    step: WorkflowStep,
    run: WorkflowRun,
    exc: BaseException,
    **extra: Any,
) -> None:
    now = datetime.now(timezone.utc)
    error_json = build_step_error_json(step, run, exc, **extra)
    step.status = "failed"
    step.finished_at = now
    step.error_json = error_json
    run.status = "failed"
    run.finished_at = now
    session.commit()
    logger.error(
        "workflow_step_failed",
        step_name=step.step_name,
        run_id=str(run.id),
        category=error_json["category"],
        exception_type=error_json["exception_type"],
        error=error_json["message"],
        exc_info=exc,
    )
