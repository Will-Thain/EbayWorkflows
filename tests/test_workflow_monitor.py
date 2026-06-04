from __future__ import annotations

from ebay_workflows.gui.workflow_monitor import (
    elapsed_label_from_seconds,
    job_id_for_step,
    workflow_source_label,
)
from types import SimpleNamespace


def test_step_to_job_mapping() -> None:
    assert job_id_for_step("phase5_ocr_verification") == "phase5"
    assert job_id_for_step("unknown_step") == "unknown_step"


def test_elapsed_label_from_seconds() -> None:
    assert elapsed_label_from_seconds(45) == "45s"
    assert elapsed_label_from_seconds(125) == "2m 5s"
    assert elapsed_label_from_seconds(3725) == "1h 2m"


def test_workflow_source_label() -> None:
    active = SimpleNamespace(job_id="phase4")
    assert workflow_source_label(active, "phase4") == "GUI"  # type: ignore[arg-type]
    assert workflow_source_label(active, None) == "External"  # type: ignore[arg-type]
    assert workflow_source_label(active, "phase5") == "External"  # type: ignore[arg-type]
