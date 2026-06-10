from __future__ import annotations

from pathlib import Path

from ebay_workflows.operations.workflow_logs import list_workflow_log_files


def test_list_workflow_log_files_parses_job_id(tmp_path: Path) -> None:
    log = tmp_path / "20260101T120000Z_phase5.log"
    log.write_text("hello", encoding="utf-8")
    rows = list_workflow_log_files(tmp_path)
    assert len(rows) == 1
    assert rows[0].job_id == "phase5"
    assert rows[0].size_bytes == 5
