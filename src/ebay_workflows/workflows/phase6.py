from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import CardPrice, ImageDetection, ScryfallCard
from ..recognition.catalog_index import catalog_from_scryfall_rows
from ..recognition import CardMatchEntry, ScryfallTitleIndex, build_set_collector_index
from ..recognition.listing_lot_detection import (
    detect_lot_cards_from_image,
    detected_lot_cards_to_payload,
)
from ..operations.listing_filters import is_bulk_lot_title
from ..operations.metrics import merge_phase_counters
from ..operations.progress_report import emit_progress
from ..operations.workflow_progress import publish_step_progress
from ..operations.workflow_run import begin_phase_run, utc_now
from ..operations.workflow_sample import fetch_limited_listing_images, fetch_limited_listings, sample_scope_label
from ..workflow_errors import fail_workflow_step
from .phase6_lot import load_mock_lot, process_lot_cards_for_image


def run_phase6_bulk_lot_detection(
    session: Session,
    settings: Settings,
    mock_lot_file: str | None = None,
    use_real_lot_detection: bool = False,
) -> str:
    run, step = begin_phase_run(
        session,
        workflow_default_name=settings.workflow_default_name,
        phase_number=6,
        step_name="phase6_bulk_lot_detection",
        input_config={
            "mock_lot_file": mock_lot_file,
            "use_real_lot_detection": use_real_lot_detection,
        },
    )

    try:
        listing_images = fetch_limited_listing_images(session, settings)
        sample_label = sample_scope_label(settings)
        if sample_label:
            print(
                f"ebay-workflows-info Phase 6 sample scope: {sample_label} "
                f"({len(listing_images)} images selected)",
                flush=True,
            )
        image_by_url = {img.source_url: img for img in listing_images}
        listings = fetch_limited_listings(session, settings)
        listing_by_id = {listing.id: listing for listing in listings}
        cards = session.execute(select(ScryfallCard)).scalars().all()
        card_by_id = {str(card.id): card for card in cards}
        title_index = ScryfallTitleIndex.from_entries(
            [
                CardMatchEntry(
                    card_id=str(card.id),
                    name=card.name,
                    set_code=card.set_code,
                    collector_number=card.collector_number,
                )
                for card in cards
            ]
        )
        set_collector_index = build_set_collector_index(
            [(str(card.id), card.set_code, card.collector_number) for card in cards]
        )
        catalog = catalog_from_scryfall_rows(cards)
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
            lot_rows = load_mock_lot(mock_lot_file)
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
                d, o, _ = process_lot_cards_for_image(
                    session,
                    listing_image,
                    listing,
                    detected_cards,
                    catalog,
                    title_index,
                    card_by_id,
                    latest_price_by_card,
                    model_version="phase6_mock_v1",
                    engine_name="mock",
                    settings=settings,
                    set_collector_index=set_collector_index,
                )
                if d or o:
                    detections_created += d
                    ocr_rows_created += o
                    listings_updated += 1
        elif use_real_lot_detection:
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
                if settings.phase6_skip_analyzed_images:
                    has_lot = session.execute(
                        select(ImageDetection.id).where(
                            ImageDetection.listing_image_id == img.id,
                            ImageDetection.detection_type == "lot_card",
                        ).limit(1)
                    ).first()
                    if has_lot:
                        continue
                eligible.append(img)
            workers = max(1, int(getattr(settings, "pipeline_max_image_workers", 4)))

            from ..recognition.embedding_index import index_exists, search_similar_cards

            search_fn = None
            if index_exists(settings.faiss_index_path):

                def _search(path: str):
                    return search_similar_cards(path, settings, top_k=settings.faiss_top_k)

                search_fn = _search

            def _detect_payload(image_id: str, local_path: str) -> tuple[str, list[dict[str, Any]]]:
                lot_cards = detect_lot_cards_from_image(
                    local_path,
                    crop_dir,
                    catalog,
                    search_fn=search_fn,
                    ocr_engine=settings.ocr_engine,
                    tesseract_cmd=settings.tesseract_cmd,
                    min_region_score=settings.image_min_region_score,
                    allow_full_frame_fallback=settings.image_allow_full_frame_fallback,
                    settings=settings,
                )
                return image_id, detected_lot_cards_to_payload(lot_cards)

            detection_results: dict[str, list[dict[str, Any]]] = {}
            pending_tasks = [(str(image.id), image.local_path or "") for image in eligible]
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(_detect_payload, image_id, local_path): image_id
                    for image_id, local_path in pending_tasks
                }
                total = len(futures)
                if total:
                    emit_progress(0, total, unit="images")
                    publish_step_progress(session, step, 0, total, unit="images")
                for index, future in enumerate(as_completed(futures), start=1):
                    image_id, payload = future.result()
                    detection_results[image_id] = payload
                    if index % 5 == 0 or index == total:
                        emit_progress(index, total, unit="images")
                        publish_step_progress(session, step, index, total, unit="images")

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
                d, o, _ = process_lot_cards_for_image(
                    session,
                    listing_image,
                    listing,
                    payload,
                    catalog,
                    title_index,
                    card_by_id,
                    latest_price_by_card,
                    model_version="phase6_opencv_v1",
                    engine_name=settings.ocr_engine,
                    settings=settings,
                    set_collector_index=set_collector_index,
                )
                if d or o:
                    detections_created += d
                    ocr_rows_created += o
                    listings_updated += 1
        else:
            raise ValueError("Provide --mock-lot-file or enable --use-real-lot-detection.")

        step.status = "succeeded"
        step.finished_at = utc_now()
        metrics = merge_phase_counters(
            {},
            detections_created=detections_created,
            ocr_rows_created=ocr_rows_created,
            listings_updated=listings_updated,
            images_processed=images_processed,
            pipeline_max_image_workers=getattr(settings, "pipeline_max_image_workers", 4),
        )
        if use_real_lot_detection and not mock_lot_file:
            metrics["images_skipped_no_visible_cards"] = images_skipped_no_visible_cards
            metrics["listings_skipped_not_bulk"] = listings_skipped_not_bulk
        step.metrics_json = metrics
        run.status = "succeeded"
        run.finished_at = utc_now()
        session.commit()
    except Exception as exc:  # noqa: BLE001
        fail_workflow_step(session, step, run, exc)
        raise

    return str(run.id)
