from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(0x100000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@contextmanager
def pipeline_run_lock(lock_path: str | Path) -> Iterator[None]:
    """Exclusive lock so only one pipeline ingest runs at a time."""
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            other_pid = int(payload.get("pid", 0))
            if _pid_alive(other_pid):
                started = payload.get("started_at", "unknown")
                raise RuntimeError(
                    f"Another pipeline is running (pid={other_pid}, started={started}). "
                    f"Lock: {path}"
                )
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    path.write_text(
        json.dumps({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    try:
        yield
    finally:
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if int(payload.get("pid", 0)) == os.getpid():
                    path.unlink(missing_ok=True)
            except (json.JSONDecodeError, ValueError, OSError):
                path.unlink(missing_ok=True)
