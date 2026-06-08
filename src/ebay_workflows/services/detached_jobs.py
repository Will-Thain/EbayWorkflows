from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from ..cli_launch import project_root, resolve_cli_launch
from ..gui.workflow_catalog import WORKFLOW_JOBS, build_argv

logger = structlog.get_logger(__name__)


def detached_job_log_path(log_dir: str | Path, job_id: str) -> Path:
    root = Path(log_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_job = job_id.replace("/", "_")
    return root / f"{stamp}_{safe_job}.log"


def spawn_cli_job_detached(
    job_id: str,
    params: dict[str, Any] | None = None,
    *,
    log_dir: str | Path | None = None,
) -> Path | None:
    if job_id not in WORKFLOW_JOBS:
        raise ValueError(f"Unknown job_id: {job_id}")
    argv = build_argv(job_id, params or {})
    program, args = resolve_cli_launch(argv)
    log_path = detached_job_log_path(log_dir, job_id) if log_dir else None
    kwargs: dict[str, Any] = {
        "cwd": str(project_root()),
    }
    if log_path is not None:
        log_handle = log_path.open("a", encoding="utf-8")
        log_handle.write(f"--- scheduled spawn: {job_id} ---\n")
        log_handle.flush()
        kwargs["stdout"] = log_handle
        kwargs["stderr"] = subprocess.STDOUT
    else:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    subprocess.Popen([program, *args], **kwargs)
    if log_path is not None:
        logger.info("detached_job_spawned", job_id=job_id, log_path=str(log_path))
    return log_path
