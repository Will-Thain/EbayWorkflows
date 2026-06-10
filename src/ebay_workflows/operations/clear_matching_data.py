from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import ImageDetection, ListingCardCandidate, ListingScore, OcrResult


@dataclass(slots=True)
class ClearMatchingReport:
    ocr_results_deleted: int
    image_detections_deleted: int
    listing_candidates_deleted: int
    listing_scores_deleted: int
    export_files_deleted: int

    @property
    def total_rows_deleted(self) -> int:
        return (
            self.ocr_results_deleted
            + self.image_detections_deleted
            + self.listing_candidates_deleted
            + self.listing_scores_deleted
        )


def count_matching_artifacts(session: Session) -> dict[str, int]:
    return {
        "ocr_results": session.execute(select(func.count()).select_from(OcrResult)).scalar_one(),
        "image_detections": session.execute(select(func.count()).select_from(ImageDetection)).scalar_one(),
        "listing_card_candidates": session.execute(
            select(func.count()).select_from(ListingCardCandidate)
        ).scalar_one(),
        "listing_scores": session.execute(select(func.count()).select_from(ListingScore)).scalar_one(),
    }


def clear_matching_artifacts(
    session: Session,
    *,
    export_dir: str | Path | None = "./data/exports",
) -> ClearMatchingReport:
    """
    Remove pipeline match/score artifacts while keeping listings, images, Scryfall, and prices.

    Deletes (in FK-safe order): ocr_results, image_detections, listing_card_candidates, listing_scores.
    """
    ocr_deleted = session.execute(delete(OcrResult)).rowcount or 0
    detections_deleted = session.execute(delete(ImageDetection)).rowcount or 0
    candidates_deleted = session.execute(delete(ListingCardCandidate)).rowcount or 0
    scores_deleted = session.execute(delete(ListingScore)).rowcount or 0
    session.commit()

    exports_removed = 0
    if export_dir is not None:
        export_path = Path(export_dir)
        if export_path.is_dir():
            for path in export_path.glob("ranked*.json"):
                path.unlink(missing_ok=True)
                exports_removed += 1

    return ClearMatchingReport(
        ocr_results_deleted=max(ocr_deleted, 0),
        image_detections_deleted=max(detections_deleted, 0),
        listing_candidates_deleted=max(candidates_deleted, 0),
        listing_scores_deleted=max(scores_deleted, 0),
        export_files_deleted=exports_removed,
    )
