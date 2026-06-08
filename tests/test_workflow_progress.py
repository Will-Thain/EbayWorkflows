from __future__ import annotations

from types import SimpleNamespace

from ebay_workflows.services.progress_report import ProgressSnapshot
from ebay_workflows.services.workflow_progress import progress_from_step_metrics, publish_step_progress


def test_publish_and_read_step_metrics() -> None:
    step = SimpleNamespace(metrics_json=None)
    session = _FakeSession()
    publish_step_progress(session, step, 12, 100, unit="listings")  # type: ignore[arg-type]
    assert step.metrics_json["progress_current"] == 12
    assert step.metrics_json["progress_total"] == 100
    snap = progress_from_step_metrics(step)  # type: ignore[arg-type]
    assert snap == ProgressSnapshot(current=12, total=100, unit="listings")


class _FakeSession:
    def commit(self) -> None:
        pass
