from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import Settings
from .models import (
    ImageDetection,
    ListingCardCandidate,
    ListingImage,
    OcrResult,
    WorkflowRun,
    WorkflowStep,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_mock_ocr(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Mock OCR file must be a list of objects.")
    return payload


def _extract_title_from_image(local_path: str) -> tuple[str | None, float]:
    image_path = Path(local_path)
    if not image_path.exists():
        return None, 0.0

    try:
        import cv2  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on local runtime
        raise RuntimeError(
            "Real OCR mode requires opencv-python and pytesseract to be installed."
        ) from exc

    image = cv2.imread(str(image_path))
    if image is None:
        return None, 0.0

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    text = pytesseract.image_to_string(thresh, config="--psm 6").strip()
    if not text:
        return None, 0.0

    # Use first non-empty line as a simple title approximation for MVP.
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line:
        return None, 0.0
    confidence = min(0.95, max(0.4, len(first_line) / 40))
    return first_line, confidence


def _update_candidate_confidence(candidate: ListingCardCandidate, ocr_title: str) -> None:
    if not candidate.scryfall_card or not candidate.scryfall_card.name:
        return
    similarity = fuzz.WRatio(ocr_title.lower(), candidate.scryfall_card.name.lower()) / 100.0
    confidence = float(candidate.confidence_score)
    if similarity >= 0.8:
        confidence = min(1.0, confidence + 0.1)
    elif similarity < 0.55:
        confidence = max(0.0, confidence - 0.1)
    candidate.confidence_score = confidence

    evidence = dict(candidate.evidence_json or {})
    evidence["ocr_verification"] = {
        "ocr_title": ocr_title,
        "similarity": similarity,
        "method": "rapidfuzz_wratio",
    }
    candidate.evidence_json = evidence


def run_phase5_ocr_verification(
    session: Session,
    settings: Settings,
    mock_ocr_file: str | None = None,
    use_real_ocr: bool = False,
) -> str:
    run = WorkflowRun(
        workflow_name=f"{settings.workflow_default_name}_phase5",
        status="running",
        input_config_json={"mock_ocr_file": mock_ocr_file, "use_real_ocr": use_real_ocr},
        started_at=_now(),
    )
    session.add(run)
    session.flush()

    step = WorkflowStep(
        run_id=run.id,
        step_name="phase5_ocr_verification",
        phase_number=5,
        status="running",
        attempt=1,
        started_at=_now(),
    )
    session.add(step)
    session.flush()

    try:
        listing_images = session.execute(select(ListingImage)).scalars().all()
        detections_created = 0
        ocr_rows_created = 0
        candidates_updated = 0

        def _process_title(
            listing_image: ListingImage,
            title: str,
            confidence: float,
            model_version: str,
            engine_name: str,
            engine_version: str,
            set_code: str = "",
            collector_number: str = "",
        ) -> None:
            nonlocal detections_created, ocr_rows_created, candidates_updated

            existing_detection_ids = session.execute(
                select(ImageDetection.id).where(
                    ImageDetection.listing_image_id == listing_image.id,
                    ImageDetection.detection_type == "card_region",
                )
            ).scalars().all()
            if existing_detection_ids:
                session.execute(delete(OcrResult).where(OcrResult.detection_id.in_(existing_detection_ids)))
                session.execute(delete(ImageDetection).where(ImageDetection.id.in_(existing_detection_ids)))

            detection = ImageDetection(
                listing_image_id=listing_image.id,
                detection_type="card_region",
                bbox_x=0,
                bbox_y=0,
                bbox_w=1,
                bbox_h=1,
                detection_score=confidence,
                model_version=model_version,
            )
            session.add(detection)
            session.flush()
            detections_created += 1

            if title:
                session.add(
                    OcrResult(
                        detection_id=detection.id,
                        field_type="title",
                        raw_text=title,
                        normalized_text=title.lower(),
                        confidence_score=confidence,
                        engine_name=engine_name,
                        engine_version=engine_version,
                        region_image_path=listing_image.local_path,
                    )
                )
                ocr_rows_created += 1
            if set_code:
                session.add(
                    OcrResult(
                        detection_id=detection.id,
                        field_type="set_code",
                        raw_text=set_code,
                        normalized_text=set_code.lower(),
                        confidence_score=confidence,
                        engine_name=engine_name,
                        engine_version=engine_version,
                        region_image_path=listing_image.local_path,
                    )
                )
                ocr_rows_created += 1
            if collector_number:
                session.add(
                    OcrResult(
                        detection_id=detection.id,
                        field_type="collector_number",
                        raw_text=collector_number,
                        normalized_text=collector_number.lower(),
                        confidence_score=confidence,
                        engine_name=engine_name,
                        engine_version=engine_version,
                        region_image_path=listing_image.local_path,
                    )
                )
                ocr_rows_created += 1

            if title:
                candidates = session.execute(
                    select(ListingCardCandidate).where(ListingCardCandidate.listing_id == listing_image.listing_id)
                ).scalars().all()
                for candidate in candidates:
                    _update_candidate_confidence(candidate, title)
                    candidates_updated += 1

        if mock_ocr_file:
            mock_rows = _load_mock_ocr(mock_ocr_file)
            by_source_url = {row.source_url: row for row in listing_images}
            for row in mock_rows:
                source_url = row.get("source_url")
                if not source_url:
                    continue
                listing_image = by_source_url.get(source_url)
                if not listing_image:
                    continue
                _process_title(
                    listing_image=listing_image,
                    title=(row.get("title") or "").strip(),
                    confidence=float(row.get("confidence", 0.9)),
                    model_version="phase5_mock_v1",
                    engine_name="mock",
                    engine_version="v1",
                    set_code=(row.get("set_code") or "").strip(),
                    collector_number=(row.get("collector_number") or "").strip(),
                )
        elif use_real_ocr:
            for listing_image in listing_images:
                if not listing_image.local_path:
                    continue
                title, confidence = _extract_title_from_image(listing_image.local_path)
                if not title:
                    continue
                _process_title(
                    listing_image=listing_image,
                    title=title,
                    confidence=confidence,
                    model_version="phase5_real_ocr_v1",
                    engine_name="pytesseract",
                    engine_version="v1",
                )
        else:
            raise ValueError("Provide --mock-ocr-file or enable --use-real-ocr.")

        step.status = "succeeded"
        step.finished_at = _now()
        step.metrics_json = {
            "detections_created": detections_created,
            "ocr_rows_created": ocr_rows_created,
            "candidates_updated": candidates_updated,
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

