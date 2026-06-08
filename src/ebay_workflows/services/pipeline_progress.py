from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ImageDetection, ListingImage, OcrResult
from .match_stats import collect_match_stats


def collect_pipeline_progress(session: Session) -> dict[str, Any]:
    """Read-only snapshot of pipeline table counts for operator monitoring."""
    stats = collect_match_stats(session)
    stats["listing_images"] = int(
        session.execute(select(func.count()).select_from(ListingImage)).scalar_one()
    )
    stats["image_detections"] = int(
        session.execute(select(func.count()).select_from(ImageDetection)).scalar_one()
    )
    stats["ocr_results"] = int(
        session.execute(select(func.count()).select_from(OcrResult)).scalar_one()
    )
    stats["lot_detections"] = int(
        session.execute(
            select(func.count())
            .select_from(ImageDetection)
            .where(ImageDetection.detection_type == "lot_card")
        ).scalar_one()
    )
    return stats
