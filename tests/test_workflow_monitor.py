from __future__ import annotations

import sys

from ebay_workflows.gui.workflow_monitor import (
    elapsed_label_from_seconds,
    job_id_for_step,
    workflow_control_flags,
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


def test_workflow_control_flags_gui_running() -> None:
    flags = workflow_control_flags(
        source="GUI",
        runner_busy=True,
        runner_paused=False,
        matches_local_job=True,
    )
    assert flags["can_stop"] is True
    assert flags["can_pause"] is (sys.platform == "win32")
    assert flags["can_resume"] is False


def test_workflow_control_flags_gui_paused() -> None:
    flags = workflow_control_flags(
        source="GUI",
        runner_busy=True,
        runner_paused=True,
        matches_local_job=True,
    )
    assert flags["can_stop"] is True
    assert flags["can_pause"] is False
    assert flags["can_resume"] is (sys.platform == "win32")


def test_workflow_control_flags_external() -> None:
    flags = workflow_control_flags(
        source="External",
        runner_busy=True,
        runner_paused=False,
        matches_local_job=False,
    )
    assert flags == {"can_stop": False, "can_pause": False, "can_resume": False}
