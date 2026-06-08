from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import ImageDetection, Listing, ListingCardCandidate, ListingImage
from .presenters import is_safe_cache_path


@dataclass(slots=True)
class DetectionDetail:
    id: str
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    detection_score: float
    ocr_title: str | None = None
    crop_path: str | None = None


@dataclass(slots=True)
class ListingImageDetail:
    id: str
    local_path: str
    index: int
    detections: list[DetectionDetail] = field(default_factory=list)


@dataclass(slots=True)
class FaissMatchDetail:
    scryfall_id: str
    card_name: str | None
    score: float


@dataclass(slots=True)
class MatchDetail:
    rank_position: int
    scryfall_id: str | None
    card_name: str | None
    set_code: str | None
    match_score: float
    confidence_score: float
    price_amount: float | None
    price_currency: str | None
    price_type: str | None
    faiss_matches: list[FaissMatchDetail] = field(default_factory=list)
    ocr_title: str | None = None
    ocr_similarity: float | None = None
    embedding_agreement: bool | None = None
    pricing_eligible: bool = True
    pricing_reject_reason: str | None = None
    image_verified: bool = False
    image_verification_source: str | None = None
    verification_listing_image_id: str | None = None
    verification_detection_id: str | None = None
    verification_region_path: str | None = None


@dataclass(slots=True)
class ListingDetail:
    listing_id: str
    title: str
    images: list[ListingImageDetail]
    matches: list[MatchDetail]


def _parse_faiss_matches(evidence: dict[str, Any]) -> list[FaissMatchDetail]:
    raw = evidence.get("faiss_matches") or []
    matches: list[FaissMatchDetail] = []
    if not isinstance(raw, list):
        return matches
    for item in raw:
        if not isinstance(item, dict):
            continue
        matches.append(
            FaissMatchDetail(
                scryfall_id=str(item.get("scryfall_id", "")),
                card_name=item.get("card_name"),
                score=float(item.get("score", 0.0)),
            )
        )
    return matches


def _parse_match(candidate: Any) -> MatchDetail:
    evidence = dict(candidate.evidence_json or {})
    card = candidate.scryfall_card
    card_name = card.name if card else None
    set_code = card.set_code if card else None

    price_amount: float | None = None
    price_currency: str | None = None
    price_type: str | None = None
    cm = evidence.get("cardmarket_price")
    if isinstance(cm, dict):
        price_amount = float(cm["price_amount"]) if cm.get("price_amount") is not None else None
        price_currency = cm.get("currency")
        price_type = cm.get("price_type")

    ocr = evidence.get("ocr_verification")
    ocr_title: str | None = None
    ocr_similarity: float | None = None
    if isinstance(ocr, dict):
        ocr_title = ocr.get("ocr_title")
        if ocr.get("similarity") is not None:
            ocr_similarity = float(ocr["similarity"])

    embedding_agreement = evidence.get("embedding_agreement")
    if embedding_agreement is not None:
        embedding_agreement = bool(embedding_agreement)

    return MatchDetail(
        rank_position=int(candidate.rank_position),
        scryfall_id=str(candidate.scryfall_id) if candidate.scryfall_id else None,
        card_name=card_name,
        set_code=set_code,
        match_score=float(candidate.match_score),
        confidence_score=float(candidate.confidence_score),
        price_amount=price_amount,
        price_currency=price_currency,
        price_type=price_type,
        faiss_matches=_parse_faiss_matches(evidence),
        ocr_title=ocr_title,
        ocr_similarity=ocr_similarity,
        embedding_agreement=embedding_agreement,
        pricing_eligible=bool(evidence.get("pricing_eligible", True)),
        pricing_reject_reason=evidence.get("pricing_reject_reason"),
        image_verified=bool(evidence.get("image_verified")),
        image_verification_source=evidence.get("image_verification_source"),
        verification_listing_image_id=evidence.get("verification_listing_image_id"),
        verification_detection_id=evidence.get("verification_detection_id"),
        verification_region_path=evidence.get("verification_region_path"),
    )


def _detection_detail(detection: ImageDetection, cache_dir: str) -> DetectionDetail:
    ocr_title: str | None = None
    crop_path: str | None = None
    for ocr in detection.ocr_results:
        if ocr.field_type == "title" and ocr.raw_text:
            ocr_title = ocr.raw_text
        if ocr.region_image_path and is_safe_cache_path(ocr.region_image_path, cache_dir):
            crop_path = ocr.region_image_path
    return DetectionDetail(
        id=str(detection.id),
        bbox_x=float(detection.bbox_x),
        bbox_y=float(detection.bbox_y),
        bbox_w=float(detection.bbox_w),
        bbox_h=float(detection.bbox_h),
        detection_score=float(detection.detection_score),
        ocr_title=ocr_title,
        crop_path=crop_path,
    )


def detection_for_match(detections: list[DetectionDetail], match: MatchDetail) -> int | None:
    """Return index of the best detection to highlight for a match."""
    if not detections:
        return None

    if match.verification_detection_id:
        for idx, det in enumerate(detections):
            if det.id == match.verification_detection_id:
                return idx

    try:
        from rapidfuzz import fuzz

        best_idx: int | None = None
        best_score = 0.0
        if match.card_name:
            for idx, det in enumerate(detections):
                if not det.ocr_title:
                    continue
                score = fuzz.WRatio(det.ocr_title.lower(), match.card_name.lower()) / 100.0
                if score > best_score:
                    best_score = score
                    best_idx = idx
        if best_idx is not None and best_score >= 0.5:
            return best_idx
    except ImportError:
        pass

    idx = match.rank_position - 1
    if 0 <= idx < len(detections):
        return idx
    return 0


def fetch_listing_detail(
    session: Session,
    listing_id: uuid.UUID,
    *,
    image_cache_dir: str,
) -> ListingDetail | None:
    listing = session.execute(
        select(Listing)
        .where(Listing.id == listing_id)
        .options(
            joinedload(Listing.images).joinedload(ListingImage.detections).joinedload(ImageDetection.ocr_results),
            joinedload(Listing.card_candidates).joinedload(ListingCardCandidate.scryfall_card),
        )
    ).unique().scalar_one_or_none()
    if not listing:
        return None

    images: list[ListingImageDetail] = []
    image_index = 0
    for img in sorted(listing.images, key=lambda row: row.source_url):
        if img.download_status != "succeeded" or not img.local_path:
            continue
        if not is_safe_cache_path(img.local_path, image_cache_dir):
            continue
        detections = sorted(
            [_detection_detail(det, image_cache_dir) for det in img.detections],
            key=lambda d: d.detection_score,
            reverse=True,
        )
        images.append(
            ListingImageDetail(
                id=str(img.id),
                local_path=img.local_path,
                index=image_index,
                detections=detections,
            )
        )
        image_index += 1

    matches = sorted(
        [_parse_match(candidate) for candidate in listing.card_candidates if (candidate.evidence_json or {}).get("image_verified")],
        key=lambda m: m.rank_position,
    )

    return ListingDetail(
        listing_id=str(listing.id),
        title=listing.title,
        images=images,
        matches=matches,
    )
