from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import (
    CardPrice,
    ImageDetection,
    Listing,
    ListingImage,
    ListingScore,
    OcrResult,
    ScryfallCard,
    WorkflowRun,
    WorkflowStep,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_decimal(value: float | Decimal | None, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _load_mock_lot(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Mock lot file must be a list of listing image entries.")
    return payload


def _best_card_match(title: str, cards: list[ScryfallCard]) -> tuple[ScryfallCard | None, float]:
    best_card: ScryfallCard | None = None
    best_score = 0.0
    for card in cards:
        score = fuzz.WRatio(title.lower(), card.name.lower()) / 100.0
        if score > best_score:
            best_score = score
            best_card = card
    if best_score < 0.55:
        return None, 0.0
    return best_card, best_score


def run_phase6_bulk_lot_detection(
    session: Session,
    settings: Settings,
    mock_lot_file: str,
) -> str:
    run = WorkflowRun(
        workflow_name=f"{settings.workflow_default_name}_phase6",
        status="running",
        input_config_json={"mock_lot_file": mock_lot_file},
        started_at=_now(),
    )
    session.add(run)
    session.flush()

    step = WorkflowStep(
        run_id=run.id,
        step_name="phase6_bulk_lot_detection",
        phase_number=6,
        status="running",
        attempt=1,
        started_at=_now(),
    )
    session.add(step)
    session.flush()

    try:
        lot_rows = _load_mock_lot(mock_lot_file)
        listing_images = session.execute(select(ListingImage)).scalars().all()
        image_by_url = {img.source_url: img for img in listing_images}
        listings = session.execute(select(Listing)).scalars().all()
        listing_by_id = {listing.id: listing for listing in listings}
        cards = session.execute(select(ScryfallCard)).scalars().all()
        prices = session.execute(select(CardPrice)).scalars().all()
        latest_price_by_card: dict[str, CardPrice] = {}
        for price in prices:
            key = str(price.scryfall_id)
            current = latest_price_by_card.get(key)
            if current is None or price.price_timestamp > current.price_timestamp:
                latest_price_by_card[key] = price

        detections_created = 0
        ocr_rows_created = 0
        listings_updated = 0

        for lot in lot_rows:
            source_url = lot.get("source_url")
            if not source_url:
                continue
            listing_image = image_by_url.get(source_url)
            if not listing_image:
                continue
            listing = listing_by_id.get(listing_image.listing_id)
            if not listing:
                continue

            detected_cards = lot.get("detected_cards") or []
            lot_total = Decimal("0")
            confidence_sum = Decimal("0")
            confidence_count = 0
            lot_items: list[dict[str, Any]] = []

            for card_item in detected_cards:
                title = (card_item.get("title") or "").strip()
                if not title:
                    continue
                quantity = int(card_item.get("quantity", 1))
                detection_confidence = Decimal(str(card_item.get("confidence", 0.75)))
                detection = ImageDetection(
                    listing_image_id=listing_image.id,
                    detection_type="lot_card",
                    bbox_x=0,
                    bbox_y=0,
                    bbox_w=1,
                    bbox_h=1,
                    detection_score=detection_confidence,
                    model_version="phase6_mock_v1",
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
                        engine_name="mock",
                        engine_version="v1",
                        region_image_path=listing_image.local_path,
                    )
                )
                ocr_rows_created += 1

                card_match, match_score = _best_card_match(title, cards)
                unit_price = Decimal("0")
                if card_match:
                    cm_price = latest_price_by_card.get(str(card_match.id))
                    if cm_price:
                        unit_price = _to_decimal(cm_price.price_amount)
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
                    }
                )

            if not lot_items:
                continue

            listing_cost = _to_decimal(listing.price_amount) + _to_decimal(listing.shipping_amount)
            ev_raw = lot_total - listing_cost
            confidence_score = confidence_sum / Decimal(str(max(confidence_count, 1)))
            confidence_score = max(Decimal("0"), min(Decimal("1"), confidence_score))
            risk_score = Decimal("1") - confidence_score
            ev_adjusted = ev_raw * confidence_score

            score = session.execute(
                select(ListingScore).where(ListingScore.listing_id == listing.id)
            ).scalar_one_or_none()
            explanation = {
                "listing_cost": float(listing_cost),
                "lot_total_value": float(lot_total),
                "lot_items": lot_items,
            }
            if score:
                score.ev_raw = ev_raw
                score.ev_adjusted = ev_adjusted
                score.confidence_score = confidence_score
                score.risk_score = risk_score
                score.rank_value = ev_adjusted
                score.scoring_version = "v2_lot"
                score.explanation_json = explanation
                score.updated_at = _now()
            else:
                session.add(
                    ListingScore(
                        listing_id=listing.id,
                        ev_raw=ev_raw,
                        ev_adjusted=ev_adjusted,
                        confidence_score=confidence_score,
                        risk_score=risk_score,
                        rank_value=ev_adjusted,
                        scoring_version="v2_lot",
                        explanation_json=explanation,
                        updated_at=_now(),
                    )
                )
            listings_updated += 1

        step.status = "succeeded"
        step.finished_at = _now()
        step.metrics_json = {
            "detections_created": detections_created,
            "ocr_rows_created": ocr_rows_created,
            "listings_updated": listings_updated,
        }
        run.status = "succeeded"
        run.finished_at = _now()
        session.commit()
    except Exception as exc:  # noqa: BLE001
        step.status = "failed"
        step.finished_at = _now()
        step.error_json = {"message": str(exc)}
        run.status = "failed"
        run.finished_at = _now()
        session.commit()
        raise

    return str(run.id)

