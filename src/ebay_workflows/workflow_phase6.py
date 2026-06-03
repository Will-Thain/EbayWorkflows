from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import delete, select
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
from .services.bulk_lot_detection import (
    detect_lot_cards_from_image,
    detected_lot_cards_to_payload,
)
from .services.ev_guardrails import cap_ev_adjusted, sanitize_unit_price, title_match_allowed_for_pricing
from .services.listing_filters import is_bulk_lot_title


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


def _clear_lot_detections(session: Session, listing_image_id: Any) -> None:
    previous_lot_detection_ids = session.execute(
        select(ImageDetection.id).where(
            ImageDetection.listing_image_id == listing_image_id,
            ImageDetection.detection_type == "lot_card",
        )
    ).scalars().all()
    if previous_lot_detection_ids:
        session.execute(delete(OcrResult).where(OcrResult.detection_id.in_(previous_lot_detection_ids)))
        session.execute(delete(ImageDetection).where(ImageDetection.id.in_(previous_lot_detection_ids)))


def _process_lot_cards_for_image(
    session: Session,
    listing_image: ListingImage,
    listing: Listing,
    detected_cards: list[dict[str, Any]],
    cards: list[ScryfallCard],
    latest_price_by_card: dict[str, CardPrice],
    *,
    model_version: str,
    engine_name: str,
    settings: Settings,
) -> tuple[int, int, dict[str, Any] | None]:
    """Returns detections_created, ocr_rows_created, lot_score_explanation or None."""
    if not detected_cards:
        return 0, 0, None

    _clear_lot_detections(session, listing_image.id)

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

        card_match, match_score = _best_card_match(title, cards)
        unit_price = Decimal("0")
        if card_match:
            allowed, _ = title_match_allowed_for_pricing(
                listing.title, card_match.name, float(match_score or 0), settings
            )
            if allowed:
                cm_price = latest_price_by_card.get(str(card_match.id))
                if cm_price:
                    sanitized, _ = sanitize_unit_price(
                        cm_price.price_amount,
                        match_score=float(match_score or 0),
                        settings=settings,
                    )
                    if sanitized is not None:
                        unit_price = _to_decimal(sanitized)
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

    if len(lot_items) < settings.phase6_min_lot_detections:
        return detections_created, ocr_rows_created, None

    listing_cost = _to_decimal(listing.price_amount) + _to_decimal(listing.shipping_amount)
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

    score = session.execute(
        select(ListingScore).where(ListingScore.listing_id == listing.id)
    ).scalar_one_or_none()
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
        score.updated_at = _now()
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
                updated_at=_now(),
            )
        )

    return detections_created, ocr_rows_created, explanation


def run_phase6_bulk_lot_detection(
    session: Session,
    settings: Settings,
    mock_lot_file: str | None = None,
    use_real_detection: bool = False,
) -> str:
    run = WorkflowRun(
        workflow_name=f"{settings.workflow_default_name}_phase6",
        status="running",
        input_config_json={
            "mock_lot_file": mock_lot_file,
            "use_real_detection": use_real_detection,
        },
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
        images_processed = 0
        images_skipped_no_visible_cards = 0
        listings_skipped_not_bulk = 0
        crop_dir = str(Path(settings.image_cache_dir) / "lot_crops")

        if mock_lot_file:
            lot_rows = _load_mock_lot(mock_lot_file)
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
                for card_item in detected_cards:
                    card_item.setdefault("bbox", {"x": 0, "y": 0, "w": 1, "h": 1})
                d, o, _ = _process_lot_cards_for_image(
                    session,
                    listing_image,
                    listing,
                    detected_cards,
                    cards,
                    latest_price_by_card,
                    model_version="phase6_mock_v1",
                    engine_name="mock",
                    settings=settings,
                )
                if d or o:
                    detections_created += d
                    ocr_rows_created += o
                    listings_updated += 1
        elif use_real_detection:
            eligible = []
            for img in listing_images:
                if not img.local_path:
                    continue
                listing = listing_by_id.get(img.listing_id)
                if listing is None:
                    continue
                if settings.phase6_bulk_listings_only and not is_bulk_lot_title(listing.title):
                    listings_skipped_not_bulk += 1
                    continue
                eligible.append(img)
            workers = max(1, int(getattr(settings, "pipeline_max_image_workers", 4)))

            def _detect_payload(image: ListingImage) -> tuple[str, list[dict[str, Any]]]:
                lot_cards = detect_lot_cards_from_image(
                    image.local_path or "",
                    crop_dir,
                    ocr_engine=settings.ocr_engine,
                    tesseract_cmd=settings.tesseract_cmd,
                    min_region_score=settings.image_min_region_score,
                    allow_full_frame_fallback=settings.image_allow_full_frame_fallback,
                )
                return str(image.id), detected_lot_cards_to_payload(lot_cards)

            detection_results: dict[str, list[dict[str, Any]]] = {}
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_detect_payload, image): image for image in eligible}
                total = len(futures)
                for index, future in enumerate(as_completed(futures), start=1):
                    image_id, payload = future.result()
                    detection_results[image_id] = payload
                    if index % 10 == 0 or index == total:
                        print(f"Phase 6 bulk detection: {index}/{total}")

            by_image_id = {str(img.id): img for img in eligible}
            for image_id, payload in detection_results.items():
                listing_image = by_image_id.get(image_id)
                if listing_image is None:
                    continue
                listing = listing_by_id.get(listing_image.listing_id)
                if listing is None:
                    continue
                images_processed += 1
                if not payload:
                    images_skipped_no_visible_cards += 1
                    continue
                d, o, _ = _process_lot_cards_for_image(
                    session,
                    listing_image,
                    listing,
                    payload,
                    cards,
                    latest_price_by_card,
                    model_version="phase6_opencv_v1",
                    engine_name=settings.ocr_engine,
                    settings=settings,
                )
                if d or o:
                    detections_created += d
                    ocr_rows_created += o
                    listings_updated += 1
        else:
            raise ValueError("Provide --mock-lot-file or enable --use-real-detection.")

        step.status = "succeeded"
        step.finished_at = _now()
        metrics: dict[str, Any] = {
            "detections_created": detections_created,
            "ocr_rows_created": ocr_rows_created,
            "listings_updated": listings_updated,
            "images_processed": images_processed,
            "pipeline_max_image_workers": getattr(settings, "pipeline_max_image_workers", 4),
        }
        if use_real_detection and not mock_lot_file:
            metrics["images_skipped_no_visible_cards"] = images_skipped_no_visible_cards
            metrics["listings_skipped_not_bulk"] = listings_skipped_not_bulk
        step.metrics_json = metrics
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
