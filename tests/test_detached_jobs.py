from __future__ import annotations

from pathlib import Path

from ebay_workflows.services.detached_jobs import detached_job_log_path


def test_detached_job_log_path() -> None:
    path = detached_job_log_path("./data/logs", "phase5")
    assert path.parent == Path("./data/logs")
    assert path.name.endswith("_phase5.log")
    assert "T" in path.name
