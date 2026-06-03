from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from .services.card_regions import CardRegion
from .services.embedding_index import apply_embedding_evidence, index_exists
from .services.image_analysis import ImageAnalysisResult, analyze_listing_image


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_mock_ocr(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Mock OCR file must be a list of objects.")
    return payload


def _clear_card_regions(session: Session, listing_image_id: Any) -> None:
    existing_detection_ids = session.execute(
        select(ImageDetection.id).where(
            ImageDetection.listing_image_id == listing_image_id,
            ImageDetection.detection_type == "card_region",
        )
    ).scalars().all()
    if existing_detection_ids:
        session.execute(delete(OcrResult).where(OcrResult.detection_id.in_(existing_detection_ids)))
        session.execute(delete(ImageDetection).where(ImageDetection.id.in_(existing_detection_ids)))


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
    use_embedding_match: bool = False,
) -> str:
    run = WorkflowRun(
        workflow_name=f"{settings.workflow_default_name}_phase5",
        status="running",
        input_config_json={
            "mock_ocr_file": mock_ocr_file,
            "use_real_ocr": use_real_ocr,
            "use_embedding_match": use_embedding_match,
        },
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
        images_skipped_no_visible_cards = 0
        detections_created = 0
        ocr_rows_created = 0
        candidates_updated = 0
        embedding_updates = 0
        crop_dir = str(Path(settings.image_cache_dir) / "crops")
        embedding_enabled = use_embedding_match and index_exists(settings.faiss_index_path)

        def _persist_region_detection(
            listing_image: ListingImage,
            region: CardRegion,
            fields: dict[str, tuple[str, float]],
            *,
            model_version: str,
            engine_name: str,
            engine_version: str,
        ) -> str | None:
            nonlocal detections_created, ocr_rows_created
            detection = ImageDetection(
                listing_image_id=listing_image.id,
                detection_type="card_region",
                bbox_x=region.bbox_x,
                bbox_y=region.bbox_y,
                bbox_w=region.bbox_w,
                bbox_h=region.bbox_h,
                detection_score=region.score,
                model_version=model_version,
            )
            session.add(detection)
            session.flush()
            detections_created += 1

            region_path = region.crop_path or listing_image.local_path
            best_title: str | None = None
            for field_type, (raw_text, confidence) in fields.items():
                session.add(
                    OcrResult(
                        detection_id=detection.id,
                        field_type=field_type,
                        raw_text=raw_text,
                        normalized_text=raw_text.lower(),
                        confidence_score=confidence,
                        engine_name=engine_name,
                        engine_version=engine_version,
                        region_image_path=region_path,
                    )
                )
                ocr_rows_created += 1
                if field_type == "title":
                    best_title = raw_text
            return best_title

        def _process_mock_row(listing_image: ListingImage, row: dict[str, Any]) -> None:
            nonlocal candidates_updated
            _clear_card_regions(session, listing_image.id)
            fields: dict[str, tuple[str, float]] = {}
            title = (row.get("title") or "").strip()
            confidence = float(row.get("confidence", 0.9))
            if title:
                fields["title"] = (title, confidence)
            set_code = (row.get("set_code") or "").strip()
            if set_code:
                fields["set_code"] = (set_code, confidence)
            collector_number = (row.get("collector_number") or "").strip()
            if collector_number:
                fields["collector_number"] = (collector_number, confidence)

            region = CardRegion(0, 0, 1, 1, confidence, listing_image.local_path)
            best_title = _persist_region_detection(
                listing_image,
                region,
                fields,
                model_version="phase5_mock_v1",
                engine_name="mock",
                engine_version="v1",
            )
            if best_title:
                candidates = session.execute(
                    select(ListingCardCandidate).where(ListingCardCandidate.listing_id == listing_image.listing_id)
                ).scalars().all()
                for candidate in candidates:
                    _update_candidate_confidence(candidate, best_title)
                    candidates_updated += 1

        def _persist_analysis(listing_image: ListingImage, analysis: ImageAnalysisResult) -> None:
            nonlocal candidates_updated, embedding_updates
            if analysis.skipped:
                return
            _clear_card_regions(session, listing_image.id)
            candidates = session.execute(
                select(ListingCardCandidate).where(ListingCardCandidate.listing_id == listing_image.listing_id)
            ).scalars().all()

            best_title: str | None = None
            best_confidence = 0.0
            for region_analysis in analysis.regions:
                region = region_analysis.region
                fields = region_analysis.fields
                if fields:
                    title = _persist_region_detection(
                        listing_image,
                        region,
                        fields,
                        model_version="phase5_region_ocr_v2",
                        engine_name=settings.ocr_engine,
                        engine_version="v2",
                    )
                    if title:
                        title_conf = fields.get("title", (title, 0.0))[1]
                        if title_conf >= best_confidence:
                            best_confidence = title_conf
                            best_title = title
                if region_analysis.embedding_matches:
                    embedding_updates += apply_embedding_evidence(candidates, region_analysis.embedding_matches)

            if best_title:
                for candidate in candidates:
                    _update_candidate_confidence(candidate, best_title)
                    candidates_updated += 1

        def _run_parallel_real_ocr(images: list[ListingImage]) -> list[ImageAnalysisResult]:
            eligible = [img for img in images if img.local_path]
            if not eligible:
                return []
            workers = max(1, int(getattr(settings, "pipeline_max_image_workers", 4)))
            results: list[ImageAnalysisResult] = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        analyze_listing_image,
                        listing_image_id=str(img.id),
                        listing_id=str(img.listing_id),
                        local_path=img.local_path or "",
                        crop_dir=crop_dir,
                        settings=settings,
                        use_embedding=embedding_enabled,
                    ): img
                    for img in eligible
                }
                total = len(futures)
                for index, future in enumerate(as_completed(futures), start=1):
                    results.append(future.result())
                    if index % 10 == 0 or index == total:
                        print(f"Phase 5 image analysis: {index}/{total}")
            return results

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
                _process_mock_row(listing_image, row)
        elif use_real_ocr:
            images_skipped_no_visible_cards = 0
            analyses = _run_parallel_real_ocr(listing_images)
            by_image_id = {str(img.id): img for img in listing_images}
            for analysis in analyses:
                listing_image = by_image_id.get(analysis.listing_image_id)
                if listing_image is None:
                    continue
                if analysis.skipped:
                    images_skipped_no_visible_cards += 1
                    continue
                _persist_analysis(listing_image, analysis)
        else:
            raise ValueError("Provide --mock-ocr-file or enable --use-real-ocr.")

        step.status = "succeeded"
        step.finished_at = _now()
        metrics: dict[str, Any] = {
            "detections_created": detections_created,
            "ocr_rows_created": ocr_rows_created,
            "candidates_updated": candidates_updated,
            "embedding_updates": embedding_updates,
            "embedding_enabled": embedding_enabled,
            "pipeline_max_image_workers": getattr(settings, "pipeline_max_image_workers", 4),
        }
        if use_real_ocr and not mock_ocr_file:
            metrics["images_skipped_no_visible_cards"] = images_skipped_no_visible_cards
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
