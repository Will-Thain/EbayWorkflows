from __future__ import annotations

import pytest

from ebay_workflows.operations.pipeline_lock import pipeline_run_lock


def test_pipeline_run_lock_releases_on_exit(tmp_path) -> None:
    lock_path = tmp_path / "pipeline.lock"
    with pipeline_run_lock(lock_path):
        assert lock_path.is_file()
    assert not lock_path.exists()


def test_pipeline_run_lock_raises_when_stale_lock_has_live_pid(monkeypatch, tmp_path) -> None:
    lock_path = tmp_path / "pipeline.lock"
    lock_path.write_text('{"pid": 4242, "started_at": "2026-01-01T00:00:00Z"}', encoding="utf-8")
    monkeypatch.setattr(
        "ebay_workflows.operations.pipeline_lock._pid_alive",
        lambda pid: pid == 4242,
    )
    with pytest.raises(RuntimeError, match="Another pipeline is running"):
        with pipeline_run_lock(lock_path):
            pass
