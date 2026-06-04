from __future__ import annotations

import re
from dataclasses import dataclass

_PROGRESS_STD = re.compile(
    r"ebay-workflows-progress\s+(\d+)/(\d+)(?:\s+(\S+))?",
    re.IGNORECASE,
)
_PROGRESS_LEGACY = re.compile(
    r"Phase\s+\d+\s+[^:]+:\s*(\d+)/(\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    current: int
    total: int
    unit: str = "items"

    @property
    def percent(self) -> int | None:
        if self.total <= 0:
            return None
        return min(100, int(round(100 * self.current / self.total)))


def emit_progress(current: int, total: int, *, unit: str = "items") -> None:
    """Write a machine-readable progress line for the GUI (and human logs)."""
    print(f"ebay-workflows-progress {current}/{total} {unit}", flush=True)


def parse_progress_line(line: str) -> ProgressSnapshot | None:
    text = line.strip()
    match = _PROGRESS_STD.search(text) or _PROGRESS_LEGACY.search(text)
    if not match:
        return None
    current = int(match.group(1))
    total = int(match.group(2))
    unit = "items"
    if _PROGRESS_STD.search(text) and match.lastindex and match.lastindex >= 3:
        unit = (match.group(3) or "items").strip() or "items"
    return ProgressSnapshot(current=current, total=total, unit=unit)


def format_progress_label(snapshot: ProgressSnapshot | None, *, fallback: str = "") -> str:
    if snapshot is None:
        return fallback
    pct = snapshot.percent
    pct_text = f" ({pct}%)" if pct is not None else ""
    return f"{snapshot.current:,} / {snapshot.total:,} {snapshot.unit}{pct_text}"
