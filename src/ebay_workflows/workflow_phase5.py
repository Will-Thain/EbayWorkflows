from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from mtg_card_recognition.evidence.attach import (
    candidates_for_region_evidence,
    merge_verification_provenance,
    zone_evidence_with_provenance,
)

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
from .services.embedding_index import apply_embedding_evidence, index_exists, propose_embedding_candidates
from .services.image_analysis import ImageAnalysisResult, analyze_listing_image
from .services.image_evidence import apply_per_listing_verification_gates, region_zone_evidence_matches_card
from .services.progress_report import emit_progress
from .services.workflow_progress import publish_step_progress
from .workflow_errors import fail_workflow_step


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class RegionPersistResult:
    best_title: str | None
    detection_id: Any
    region_path: str


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


def _update_candidate_confidence(
    candidate: ListingCardCandidate,
    ocr_title: str,
    *,
    listing_image_id: str | None = None,
    detection_id: str | None = None,
    region_path: str | None = None,
) -> bool:
    """Apply OCR from one crop to a single candidate. Returns True if updated."""
    if not candidate.scryfall_card or not candidate.scryfall_card.name:
        return False
    similarity = fuzz.WRatio(ocr_title.lower(), candidate.scryfall_card.name.lower()) / 100.0
    if similarity < 0.55:
        return False

    evidence = dict(candidate.evidence_json or {})
    existing = evidence.get("ocr_verification") or {}
    existing_sim = float(existing.get("similarity", 0.0))
    if similarity <= existing_sim:
        return False

    confidence = float(candidate.confidence_score)
    if similarity >= 0.8:
        confidence = min(1.0, confidence + 0.1)

    ocr_block: dict[str, Any] = {
        "ocr_title": ocr_title,
        "similarity": similarity,
        "method": "rapidfuzz_wratio",
    }
    if listing_image_id and detection_id and region_path:
        ocr_block["listing_image_id"] = listing_image_id
        ocr_block["detection_id"] = detection_id
        ocr_block["region_image_path"] = region_path
        evidence = merge_verification_provenance(
            evidence,
            listing_image_id=listing_image_id,
            detection_id=detection_id,
            region_path=region_path,
        )

    evidence["ocr_verification"] = ocr_block
    candidate.confidence_score = confidence
    candidate.evidence_json = evidence
    return True


def _attach_zone_evidence_to_candidate(
    candidate: ListingCardCandidate,
    fields: dict[str, tuple[str, float]],
    zone_evidence: dict[str, Any],
    settings: Settings,
    *,
    listing_image_id: str,
    detection_id: str,
    region_path: str,
) -> bool:
    """Attach zone OCR/symbol evidence only to candidates the region plausibly references."""
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


def _apply_region_evidence_to_candidates(
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
    """Attach OCR and zone evidence to printings tied to this crop only."""
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
        if ocr_title and _update_candidate_confidence(
            candidate,
            ocr_title,
            listing_image_id=listing_image_id,
            detection_id=detection_id,
            region_path=region_path,
        ):
            updated += 1

    zone_targets = ocr_targets if ocr_targets else list(candidates)
    for candidate in zone_targets:
        if zone_evidence and _attach_zone_evidence_to_candidate(
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
        ) -> RegionPersistResult:
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

            region_path = region.crop_path or listing_image.local_path or ""
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
            return RegionPersistResult(best_title, detection.id, region_path)

        def _persist_region_shell(
            listing_image: ListingImage,
            region: CardRegion,
            *,
            model_version: str,
        ) -> RegionPersistResult:
            nonlocal detections_created
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
            region_path = region.crop_path or listing_image.local_path or ""
            return RegionPersistResult(None, detection.id, region_path)

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
            persist = _persist_region_detection(
                listing_image,
                region,
                fields,
                model_version="phase5_mock_v1",
                engine_name="mock",
                engine_version="v1",
            )
            candidates = session.execute(
                select(ListingCardCandidate).where(ListingCardCandidate.listing_id == listing_image.listing_id)
            ).scalars().all()
            candidates_updated += _apply_region_evidence_to_candidates(
                candidates,
                listing_image_id=str(listing_image.id),
                detection_id=str(persist.detection_id),
                region_path=persist.region_path,
                ocr_title=persist.best_title,
                fields=fields,
                zone_evidence=None,
                settings=settings,
            )

        def _persist_analysis(listing_image: ListingImage, analysis: ImageAnalysisResult) -> None:
            nonlocal candidates_updated, embedding_updates
            if analysis.skipped:
                return
            _clear_card_regions(session, listing_image.id)
            candidates = session.execute(
                select(ListingCardCandidate).where(ListingCardCandidate.listing_id == listing_image.listing_id)
            ).scalars().all()

            for region_analysis in analysis.regions:
                region = region_analysis.region
                fields = region_analysis.fields
                zone_evidence = region_analysis.zone_evidence

                if fields:
                    persist = _persist_region_detection(
                        listing_image,
                        region,
                        fields,
                        model_version="phase5_region_ocr_v2",
                        engine_name=settings.ocr_engine,
                        engine_version="v2",
                    )
                elif zone_evidence:
                    persist = _persist_region_shell(
                        listing_image,
                        region,
                        model_version="phase5_region_zone_v2",
                    )
                else:
                    persist = None

                if persist is not None:
                    candidates_updated += _apply_region_evidence_to_candidates(
                        candidates,
                        listing_image_id=str(listing_image.id),
                        detection_id=str(persist.detection_id),
                        region_path=persist.region_path,
                        ocr_title=persist.best_title,
                        fields=fields,
                        zone_evidence=zone_evidence,
                        settings=settings,
                    )

                if region_analysis.embedding_matches:
                    embedding_updates += propose_embedding_candidates(
                        session,
                        listing_image.listing_id,
                        candidates,
                        region_analysis.embedding_matches,
                        settings,
                    )
                    embedding_updates += apply_embedding_evidence(
                        candidates, region_analysis.embedding_matches
                    )

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
                if total:
                    emit_progress(0, total, unit="images")
                    publish_step_progress(session, step, 0, total, unit="images")
                for index, future in enumerate(as_completed(futures), start=1):
                    results.append(future.result())
                    if index % 5 == 0 or index == total:
                        emit_progress(index, total, unit="images")
                        publish_step_progress(session, step, index, total, unit="images")
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
            images_skipped_already_analyzed = 0
            eligible_images = list(listing_images)
            if settings.phase5_skip_analyzed_images:
                filtered: list[ListingImage] = []
                for img in eligible_images:
                    has_regions = session.execute(
                        select(ImageDetection.id).where(
                            ImageDetection.listing_image_id == img.id,
                            ImageDetection.detection_type == "card_region",
                        ).limit(1)
                    ).first()
                    if has_regions:
                        images_skipped_already_analyzed += 1
                        continue
                    filtered.append(img)
                eligible_images = filtered
            analyses = _run_parallel_real_ocr(eligible_images)
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

        all_candidates = session.execute(select(ListingCardCandidate)).scalars().all()
        for candidate in all_candidates:
            if candidate.scryfall_card is None and candidate.scryfall_id:
                session.refresh(candidate, attribute_names=["scryfall_card"])
        candidates_verified, candidates_gated = apply_per_listing_verification_gates(
            all_candidates,
            settings,
        )

        step.status = "succeeded"
        step.finished_at = _now()
        metrics: dict[str, Any] = {
            "detections_created": detections_created,
            "ocr_rows_created": ocr_rows_created,
            "candidates_updated": candidates_updated,
            "embedding_updates": embedding_updates,
            "embedding_enabled": embedding_enabled,
            "pipeline_max_image_workers": getattr(settings, "pipeline_max_image_workers", 4),
            "candidates_image_verified": candidates_verified,
            "candidates_image_gated": candidates_gated,
        }
        if use_real_ocr and not mock_ocr_file:
            metrics["images_skipped_no_visible_cards"] = images_skipped_no_visible_cards
            if settings.phase5_skip_analyzed_images:
                metrics["images_skipped_already_analyzed"] = images_skipped_already_analyzed
        step.metrics_json = metrics
        run.status = "succeeded"
        run.finished_at = _now()
        session.commit()
    except Exception as exc:  # noqa: BLE001
        fail_workflow_step(session, step, run, exc)
        raise

    return str(run.id)
