from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ListingImage
from .embedding_index import index_exists

if TYPE_CHECKING:
    from ..config import Settings


def _file_age_hours(path: Path) -> float | None:
    if not path.is_file():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - mtime).total_seconds() / 3600.0


def collect_operational_health(session: Session, settings: Settings) -> dict[str, Any]:
    """Snapshot warnings for validate-env and operator dashboards."""
    health: dict[str, Any] = {}

    faiss_path = settings.faiss_index_path
    health["faiss_index_ready"] = index_exists(faiss_path)
    health["faiss_vector_count"] = 0
    if health["faiss_index_ready"]:
        meta = json.loads(Path(f"{faiss_path}.meta.json").read_text(encoding="utf-8"))
        health["faiss_vector_count"] = len(meta.get("scryfall_ids", []))
        health["faiss_build_max_cards"] = settings.faiss_build_max_cards
        if health["faiss_vector_count"] < settings.faiss_build_max_cards:
            health["faiss_index_incomplete"] = True

    cm_path = Path(settings.cardmarket_bulk_file_path)
    cm_age = _file_age_hours(cm_path)
    health["cardmarket_bulk_age_hours"] = cm_age
    if cm_age is None:
        health["cardmarket_bulk_missing"] = True
    elif cm_age > settings.cardmarket_bulk_refresh_hours:
        health["cardmarket_bulk_stale"] = True

    failed_images = int(
        session.execute(
            select(func.count()).select_from(ListingImage).where(ListingImage.download_status == "failed")
        ).scalar_one()
    )
    pending_images = int(
        session.execute(
            select(func.count()).select_from(ListingImage).where(ListingImage.download_status == "pending")
        ).scalar_one()
    )
    health["failed_image_downloads"] = failed_images
    health["pending_image_downloads"] = pending_images

    return health
