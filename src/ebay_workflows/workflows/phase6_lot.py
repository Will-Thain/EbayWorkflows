"""Phase 6 lot-card detection persistence and lot scoring helpers."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import (
    CardPrice,
    ImageDetection,
    Listing,
    ListingImage,
    ListingScore,
    OcrResult,
    ScryfallCard,
)
from ..operations.match_event_log import log_positive_match, match_log_path
from ..operations.workflow_run import utc_now
from ..persistence.repositories import ListingScoreRepository
from ..recognition import ScryfallTitleIndex
from ..recognition.listing_identifiers import (
    ParsedCardIdentifiers,
    normalize_collector_number,
    normalize_set_code,
)
from ..recognition.lot_crop_match import resolve_lot_crop_match
from ..scoring.currency import listing_total_cost_base
from ..scoring.ev_guardrails import cap_ev_adjusted, crop_match_allowed_for_pricing, sanitize_unit_price
from ..scoring.listing_condition import adjust_price_for_listing_condition


def _to_decimal(value: float | Decimal | None, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def load_mock_lot(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Mock lot file must be a list of listing image entries.")
    return payload


def best_card_match(
    title: str,
    card_item: dict[str, Any],
    catalog: Any,
    title_index: ScryfallTitleIndex,
    set_collector_index: dict[tuple[str, str], str],
    card_by_id: dict[str, ScryfallCard],
    settings: Settings,
) -> tuple[ScryfallCard | None, float, dict[str, Any]]:
    extra = ParsedCardIdentifiers(
        set_code=normalize_set_code((card_item.get("set_code") or "").strip() or None),
        collector_number=normalize_collector_number((card_item.get("collector_number") or "").strip() or None),
    )
    return resolve_lot_crop_match(
        ocr_title=title,
        crop_path=card_item.get("crop_path"),
        catalog=catalog,
        title_index=title_index,
        set_collector_index=set_collector_index,
        card_by_id=card_by_id,
        settings=settings,
        extra_identifiers=extra,
    )


def clear_lot_detections(session: Session, listing_image_id: Any) -> None:
    previous_lot_detection_ids = session.execute(
        select(ImageDetection.id).where(
            ImageDetection.listing_image_id == listing_image_id,
            ImageDetection.detection_type == "lot_card",
        )
    ).scalars().all()
    if previous_lot_detection_ids:
        session.execute(delete(OcrResult).where(OcrResult.detection_id.in_(previous_lot_detection_ids)))
        session.execute(delete(ImageDetection).where(ImageDetection.id.in_(previous_lot_detection_ids)))


def process_lot_cards_for_image(
    session: Session,
    listing_image: ListingImage,
    listing: Listing,
    detected_cards: list[dict[str, Any]],
    catalog: Any,
    title_index: ScryfallTitleIndex,
    card_by_id: dict[str, ScryfallCard],
    latest_price_by_card: dict[str, CardPrice],
    *,
    model_version: str,
    engine_name: str,
    settings: Settings,
    set_collector_index: dict[tuple[str, str], str],
) -> tuple[int, int, dict[str, Any] | None]:
    """Returns detections_created, ocr_rows_created, lot_score_explanation or None."""
    if not detected_cards:
        return 0, 0, None

    clear_lot_detections(session, listing_image.id)

    lot_total = Decimal("0")
    confidence_sum = Decimal("0")
    confidence_count = 0
    lot_items: list[dict[str, Any]] = []
    detections_created = 0
    ocr_rows_created = 0

    for card_item in detected_cards:
        title = (card_item.get("title") or "").strip()
        if not title:
            continue
        quantity = int(card_item.get("quantity", 1))
        detection_confidence = Decimal(str(card_item.get("confidence", 0.75)))
        bbox = card_item.get("bbox") or {}
        detection = ImageDetection(
            listing_image_id=listing_image.id,
            detection_type="lot_card",
            bbox_x=bbox.get("x", 0),
            bbox_y=bbox.get("y", 0),
            bbox_w=bbox.get("w", 1),
            bbox_h=bbox.get("h", 1),
            detection_score=detection_confidence,
            model_version=model_version,
        )
        session.add(detection)
        session.flush()
        detections_created += 1

        session.add(
            OcrResult(
                detection_id=detection.id,
                field_type="title",
                raw_text=title,
                normalized_text=title.lower(),
                confidence_score=detection_confidence,
                engine_name=engine_name,
                engine_version="v2",
                region_image_path=card_item.get("crop_path") or listing_image.local_path,
            )
        )
        ocr_rows_created += 1

        card_match, match_score, match_evidence = best_card_match(
            title,
            card_item,
            catalog,
            title_index,
            set_collector_index,
            card_by_id,
            settings,
        )
        if card_match:
            log_positive_match(
                event="lot_crop_match",
                phase=6,
                listing_id=str(listing.id),
                external_listing_id=listing.external_listing_id,
                listing_image_id=str(listing_image.id),
                scryfall_id=str(card_match.id),
                card_name=card_match.name,
                match_score=float(match_score or 0.0),
                source_method=match_evidence.get("match_method"),
                ocr_title=title,
                log_path=match_log_path(settings),
                **{
                    key: match_evidence[key]
                    for key in (
                        "faiss_verified",
                        "faiss_override",
                        "faiss_only_match",
                        "lot_crop_rejected",
                    )
                    if key in match_evidence
                },
            )
        unit_price = Decimal("0")
        if card_match:
            allowed, _ = crop_match_allowed_for_pricing(
                listing.title,
                card_match.name,
                float(match_score or 0),
                match_evidence,
                scryfall_id=str(card_match.id),
                scryfall_card=card_match,
                settings=settings,
            )
            if allowed:
                cm_price = latest_price_by_card.get(str(card_match.id))
                if cm_price:
                    adjusted_price, grade, multiplier = adjust_price_for_listing_condition(
                        float(cm_price.price_amount),
                        title=listing.title,
                        condition_text=listing.condition_text,
                        settings=settings,
                    )
                    sanitized, _ = sanitize_unit_price(
                        adjusted_price,
                        match_score=float(match_score or 0),
                        settings=settings,
                    )
                    if sanitized is not None:
                        unit_price = _to_decimal(sanitized)
                        match_evidence["listing_condition_grade"] = grade
                        match_evidence["condition_multiplier"] = multiplier
        subtotal = unit_price * quantity
        lot_total += subtotal
        confidence_sum += detection_confidence * Decimal(str(match_score or 1.0))
        confidence_count += 1

        lot_items.append(
            {
                "ocr_title": title,
                "quantity": quantity,
                "matched_card": card_match.name if card_match else None,
                "match_score": match_score,
                "unit_price": float(unit_price),
                "subtotal": float(subtotal),
                "match_evidence": match_evidence,
            }
        )

    if len(lot_items) < settings.phase6_min_lot_detections:
        return detections_created, ocr_rows_created, None

    listing_cost = listing_total_cost_base(listing, settings)
    ev_raw = lot_total - listing_cost
    max_lot_total = listing_cost * Decimal(str(settings.phase6_max_lot_ev_multiple))
    if lot_total > max_lot_total:
        lot_total = max_lot_total
        ev_raw = lot_total - listing_cost
    confidence_score = confidence_sum / Decimal(str(max(confidence_count, 1)))
    confidence_score = max(Decimal("0"), min(Decimal("1"), confidence_score))
    risk_score = Decimal("1") - confidence_score
    ev_adjusted = ev_raw * confidence_score
    rank_value, ev_capped = cap_ev_adjusted(ev_adjusted, listing_cost, settings)

    score = ListingScoreRepository(session).get_for_listing(listing.id)
    explanation = {
        "listing_cost": float(listing_cost),
        "lot_total_value": float(lot_total),
        "lot_items": lot_items,
        "cards_detected": len(lot_items),
    }
    if ev_capped:
        explanation["ev_capped"] = True
    if score:
        score.ev_raw = ev_raw
        score.ev_adjusted = ev_adjusted
        score.confidence_score = confidence_score
        score.risk_score = risk_score
        score.rank_value = rank_value
        score.scoring_version = "v2_lot"
        score.explanation_json = explanation
        score.updated_at = utc_now()
    else:
        session.add(
            ListingScore(
                listing_id=listing.id,
                ev_raw=ev_raw,
                ev_adjusted=ev_adjusted,
                confidence_score=confidence_score,
                risk_score=risk_score,
                rank_value=rank_value,
                scoring_version="v2_lot",
                explanation_json=explanation,
                updated_at=utc_now(),
            )
        )

    return detections_created, ocr_rows_created, explanation
