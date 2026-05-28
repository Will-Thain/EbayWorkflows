from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import ImageDetection, Listing, ListingCardCandidate, ListingImage, OcrResult


@dataclass(slots=True)
class IntegrityReport:
    checks_run: int
    issues_found: int
    details: list[str]


def run_data_integrity_checks(session: Session) -> IntegrityReport:
    details: list[str] = []
    checks_run = 0

    listings_count = session.execute(select(func.count()).select_from(Listing)).scalar_one()
    images_count = session.execute(select(func.count()).select_from(ListingImage)).scalar_one()
    candidates_count = session.execute(select(func.count()).select_from(ListingCardCandidate)).scalar_one()
    checks_run += 3
    if listings_count > 0 and images_count == 0:
        details.append("listings exist but no listing_images were found")
    if listings_count > 0 and candidates_count == 0:
        details.append("listings exist but no listing_card_candidates were found")

    orphan_detections = session.execute(
        select(func.count())
        .select_from(ImageDetection)
        .outerjoin(ListingImage, ListingImage.id == ImageDetection.listing_image_id)
        .where(ListingImage.id.is_(None))
    ).scalar_one()
    checks_run += 1
    if orphan_detections:
        details.append(f"orphan image_detections found: {orphan_detections}")

    orphan_ocr = session.execute(
        select(func.count())
        .select_from(OcrResult)
        .outerjoin(ImageDetection, ImageDetection.id == OcrResult.detection_id)
        .where(ImageDetection.id.is_(None))
    ).scalar_one()
    checks_run += 1
    if orphan_ocr:
        details.append(f"orphan ocr_results found: {orphan_ocr}")

    duplicate_title_ocr = session.execute(
        select(func.count())
        .select_from(
            select(OcrResult.detection_id)
            .where(OcrResult.field_type == "title")
            .group_by(OcrResult.detection_id)
            .having(func.count() > 1)
            .subquery()
        )
    ).scalar_one()
    checks_run += 1
    if duplicate_title_ocr:
        details.append(f"detections with duplicate title OCR rows: {duplicate_title_ocr}")

    return IntegrityReport(checks_run=checks_run, issues_found=len(details), details=details)

