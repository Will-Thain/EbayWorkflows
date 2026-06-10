from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ListingImage
from ..recognition.embedding_index import (
    count_indexable_art_cards,
    faiss_index_crop_mode,
    index_exists,
    indexed_scryfall_ids,
    load_index_meta,
)
import structlog

from .match_stats import collect_match_stats

logger = structlog.get_logger(__name__)

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
    indexed_ids = indexed_scryfall_ids(faiss_path)
    health["faiss_vector_count"] = len(indexed_ids)
    health["faiss_build_max_cards"] = settings.faiss_build_max_cards
    health["faiss_index_crop_mode"] = faiss_index_crop_mode(settings)
    meta = load_index_meta(faiss_path)
    if meta is not None:
        indexed_mode = meta.get("index_crop_mode", "full_card")
        health["faiss_indexed_crop_mode"] = indexed_mode
        if indexed_mode != faiss_index_crop_mode(settings):
            health["faiss_index_crop_mismatch"] = True
    try:
        from sqlalchemy.orm import Session as OrmSession

        if isinstance(session, OrmSession):
            health["faiss_indexable_total"] = count_indexable_art_cards(session)
            if health["faiss_indexable_total"] > health["faiss_vector_count"]:
                health["faiss_index_incomplete"] = True
    except Exception:  # noqa: BLE001
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

    from ..recognition.set_symbol_match import set_symbol_template_dir

    template_dir = set_symbol_template_dir(settings)
    template_count = len(list(template_dir.glob("*.png"))) if template_dir.is_dir() else 0
    health["set_symbol_template_count"] = template_count
    if settings.card_set_symbol_match_enabled and template_count < 50:
        health["set_symbol_templates_missing"] = True

    health["verify_name_hard_min"] = settings.verify_name_hard_min
    health["verify_name_strong_min"] = settings.verify_name_strong_min
    health["verify_symbol_strong_min"] = settings.verify_symbol_strong_min
    health["faiss_propose_candidates"] = settings.faiss_propose_candidates
    for key, value in (
        ("verify_name_hard_min", settings.verify_name_hard_min),
        ("verify_name_strong_min", settings.verify_name_strong_min),
        ("verify_symbol_strong_min", settings.verify_symbol_strong_min),
        ("align_min_confidence", settings.align_min_confidence),
        ("image_evidence_min_faiss_score", settings.image_evidence_min_faiss_score),
    ):
        if not 0.0 < float(value) <= 1.0:
            health["verify_thresholds_invalid"] = True
            health.setdefault("invalid_threshold_keys", []).append(key)

    try:
        match_stats = collect_match_stats(session)
        health["match_stats"] = match_stats
    except Exception as exc:  # noqa: BLE001
        logger.warning("health_check_match_stats_failed", error=str(exc), exc_info=exc)

    return health
