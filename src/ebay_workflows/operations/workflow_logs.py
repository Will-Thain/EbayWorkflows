from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorkflowLogFile:
    path: Path
    job_id: str | None
    modified_at: datetime
    size_bytes: int


def _parse_job_id(name: str) -> str | None:
    # {timestamp}_{job_id}.log
    if "_" not in name or not name.endswith(".log"):
        return None
    stem = name[: -len(".log")]
    parts = stem.split("_", 1)
    if len(parts) < 2:
        return None
    return parts[1] or None


def list_workflow_log_files(log_dir: str | Path, *, limit: int = 50) -> list[WorkflowLogFile]:
    root = Path(log_dir)
    if not root.is_dir():
        return []
    files = sorted(root.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows: list[WorkflowLogFile] = []
    for path in files[:limit]:
        stat = path.stat()
        rows.append(
            WorkflowLogFile(
                path=path,
                job_id=_parse_job_id(path.name),
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                size_bytes=stat.st_size,
            )
        )
    return rows
