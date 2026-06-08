from __future__ import annotations

from types import SimpleNamespace

from ebay_workflows.workflow_errors import build_operator_error_json, build_step_error_json, error_category_for
from ebay_workflows.workflow_steps import job_id_for_step


def test_job_id_for_step_mapping() -> None:
    assert job_id_for_step("phase5_ocr_verification") == "phase5"
    assert job_id_for_step("unknown_step") == "unknown_step"


def test_error_category_for_value_error() -> None:
    assert error_category_for(ValueError("bad config")) == "ConfigurationError"


def test_build_step_error_json() -> None:
    step = SimpleNamespace(step_name="phase2_title_match")
    run = SimpleNamespace(id="run-123")
    payload = build_step_error_json(step, run, RuntimeError("boom"))  # type: ignore[arg-type]
    assert payload["category"] == "WorkflowExecutionError"
    assert payload["message"] == "boom"
    assert payload["exception_type"] == "RuntimeError"
    assert payload["step_name"] == "phase2_title_match"
    assert payload["run_id"] == "run-123"


def test_build_operator_error_json() -> None:
    payload = build_operator_error_json("cleared by operator", cleared_stale=True)
    assert payload["category"] == "WorkflowExecutionError"
    assert payload["message"] == "cleared by operator"
    assert payload["cleared_stale"] is True
