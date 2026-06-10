"""Phase 5 region persistence helpers (mock path + shared attach logic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..candidates.candidate_attach import (
    candidates_for_region_evidence,
    merge_verification_provenance,
    update_candidate_ocr_confidence,
    zone_evidence_with_provenance,
)
from ..candidates.image_evidence import region_zone_evidence_matches_card
from ..config import Settings
from ..models import ImageDetection, ListingCardCandidate, OcrResult


@dataclass(slots=True)
class RegionPersistResult:
    best_title: str | None
    detection_id: Any
    region_path: str


def clear_card_regions(session: Session, listing_image_id: Any) -> None:
    existing_detection_ids = session.execute(
        select(ImageDetection.id).where(
            ImageDetection.listing_image_id == listing_image_id,
            ImageDetection.detection_type == "card_region",
        )
    ).scalars().all()
    if existing_detection_ids:
        session.execute(delete(OcrResult).where(OcrResult.detection_id.in_(existing_detection_ids)))
        session.execute(delete(ImageDetection).where(ImageDetection.id.in_(existing_detection_ids)))


def attach_zone_evidence_to_candidate(
    candidate: ListingCardCandidate,
    fields: dict[str, tuple[str, float]],
    zone_evidence: dict[str, Any],
    settings: Settings,
    *,
    listing_image_id: str,
    detection_id: str,
    region_path: str,
) -> bool:
    if not candidate.scryfall_card:
        return False
    if not region_zone_evidence_matches_card(
        zone_evidence,
        fields,
        candidate.scryfall_card,
        settings,
    ):
        return False
    zone_payload = zone_evidence_with_provenance(
        zone_evidence,
        listing_image_id=listing_image_id,
        detection_id=detection_id,
        region_path=region_path,
    )
    evidence = merge_verification_provenance(
        dict(candidate.evidence_json or {}),
        listing_image_id=listing_image_id,
        detection_id=detection_id,
        region_path=region_path,
    )
    evidence["zone_evidence"] = zone_payload
    candidate.evidence_json = evidence
    return True


def apply_region_evidence_to_candidates(
    candidates: list[ListingCardCandidate],
    *,
    listing_image_id: str,
    detection_id: str,
    region_path: str,
    ocr_title: str | None,
    fields: dict[str, tuple[str, float]],
    zone_evidence: dict[str, Any] | None,
    settings: Settings,
) -> int:
    if not candidates:
        return 0
    ocr_targets = candidates_for_region_evidence(
        candidates,
        ocr_title=ocr_title,
        fields=fields,
        zone_evidence=zone_evidence,
    )
    updated = 0
    for candidate in ocr_targets:
        if ocr_title and update_candidate_ocr_confidence(
            candidate,
            ocr_title,
            listing_image_id=listing_image_id,
            detection_id=detection_id,
            region_path=region_path,
        ):
            updated += 1
    zone_targets = ocr_targets if ocr_targets else list(candidates)
    for candidate in zone_targets:
        if zone_evidence and attach_zone_evidence_to_candidate(
            candidate,
            fields,
            zone_evidence,
            settings,
            listing_image_id=listing_image_id,
            detection_id=detection_id,
            region_path=region_path,
        ):
            updated += 1
    return updated
