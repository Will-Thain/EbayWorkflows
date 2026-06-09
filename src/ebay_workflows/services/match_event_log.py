from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

_lock = threading.Lock()
_logger = structlog.get_logger("ebay_workflows.match")


def log_positive_match(
    *,
    event: str,
    phase: int | str,
    listing_id: str,
    scryfall_id: str | None = None,
    card_name: str | None = None,
    match_score: float | None = None,
    source_method: str | None = None,
    log_path: str | Path | None = None,
    **extra: Any,
) -> None:
    """
    Record a positive card identification event.

    Writes to structlog and appends one JSON line to ``log_path`` when set.
    Intended to fire as soon as a match is identified, before pricing gates,
    verification, or ranking weights are applied.
    """
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "match_event": event,
        "phase": phase,
        "listing_id": listing_id,
        "scryfall_id": scryfall_id,
        "card_name": card_name,
        "match_score": match_score,
        "source_method": source_method,
    }
    if extra:
        payload.update(extra)

    log_fields = {k: v for k, v in payload.items() if v is not None}
    _logger.info("card_match_positive", **log_fields)

    if not log_path:
        return

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, default=str, ensure_ascii=False)
    with _lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def match_log_path(settings: Any) -> str | None:
    if not getattr(settings, "match_event_log_enabled", True):
        return None
    return getattr(settings, "match_event_log_path", None)
