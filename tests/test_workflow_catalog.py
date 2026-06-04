from __future__ import annotations

from ebay_workflows.gui.workflow_catalog import LONG_RUNNING_SCHEDULE_JOBS, WORKFLOW_JOBS, build_argv


def test_build_argv_phase3() -> None:
    argv = build_argv("phase3")
    assert argv[0] == "ebay-workflows"
    assert "phase3-join-prices" in argv


def test_workflow_catalog_has_core_jobs() -> None:
    for job_id in ("phase1", "phase4", "phase5", "export", "integrity"):
        assert job_id in WORKFLOW_JOBS


def test_long_running_schedule_jobs() -> None:
    assert "phase5" in LONG_RUNNING_SCHEDULE_JOBS
    assert "phase4" not in LONG_RUNNING_SCHEDULE_JOBS
