from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .integrations.ebay import ListingRecord, fetch_listings
from .models import Listing, ListingImage, WorkflowRun, WorkflowStep
from .services.image_cache import download_to_cache
from .services.progress_report import emit_progress
from .services.workflow_progress import publish_step_progress


def _now():
    return datetime.now(timezone.utc)


def _load_mock_listings(path: str) -> list[ListingRecord]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    records: list[ListingRecord] = []
    for item in raw:
        records.append(
            ListingRecord(
                external_listing_id=item["external_listing_id"],
                title=item["title"],
                listing_url=item["listing_url"],
                currency=item.get("currency", "GBP"),
                price_amount=float(item.get("price_amount", 0)),
                shipping_amount=float(item["shipping_amount"]) if item.get("shipping_amount") is not None else None,
                condition_text=item.get("condition_text"),
                image_urls=item.get("image_urls", []),
                raw_payload=item,
            )
        )
    return records


def run_phase1(
    session: Session,
    settings: Settings,
    query: str,
    max_pages: int,
    mock_input_file: str | None,
    download_images: bool,
) -> str:
    run = WorkflowRun(
        workflow_name=settings.workflow_default_name,
        status="running",
        input_config_json={"query": query, "max_pages": max_pages, "mock_input_file": mock_input_file},
        started_at=_now(),
    )
    session.add(run)
    session.flush()

    step = WorkflowStep(
        run_id=run.id,
        step_name="phase1_ingest",
        phase_number=1,
        status="running",
        started_at=_now(),
        attempt=1,
    )
    session.add(step)
    session.flush()

    try:
        if mock_input_file:
            records = _load_mock_listings(mock_input_file)
        elif settings.enable_ebay_api:
            records = fetch_listings(settings, query=query, max_pages=max_pages)
        else:
            raise ValueError("ENABLE_EBAY_API is false. Provide --mock-input-file to run Phase 1 without eBay.")

        inserted = 0
        updated = 0
        skipped_existing = 0
        image_rows = 0
        downloaded = 0

        total_records = len(records)
        if total_records:
            emit_progress(0, total_records, unit="listings")
            publish_step_progress(session, step, 0, total_records, unit="listings")

        for index, record in enumerate(records, start=1):
            existing = session.execute(
                select(Listing).where(Listing.external_listing_id == record.external_listing_id)
            ).scalar_one_or_none()

            if existing and settings.phase1_skip_existing_listings:
                skipped_existing += 1
                continue

            if existing:
                existing.title = record.title
                existing.listing_url = record.listing_url
                existing.currency = record.currency
                existing.price_amount = record.price_amount
                existing.shipping_amount = record.shipping_amount
                existing.condition_text = record.condition_text
                existing.raw_payload_json = record.raw_payload
                existing.last_seen_at = _now()
                listing = existing
                updated += 1
            else:
                listing = Listing(
                    source="ebay",
                    external_listing_id=record.external_listing_id,
                    title=record.title,
                    listing_url=record.listing_url,
                    currency=record.currency,
                    price_amount=record.price_amount,
                    shipping_amount=record.shipping_amount,
                    condition_text=record.condition_text,
                    raw_payload_json=record.raw_payload,
                    first_seen_at=_now(),
                    last_seen_at=_now(),
                    created_at=_now(),
                    updated_at=_now(),
                )
                session.add(listing)
                session.flush()
                inserted += 1

            for image_url in record.image_urls:
                existing_img = session.execute(
                    select(ListingImage).where(
                        ListingImage.listing_id == listing.id,
                        ListingImage.source_url == image_url,
                    )
                ).scalar_one_or_none()
                if existing_img:
                    continue

                img = ListingImage(
                    listing_id=listing.id,
                    source_url=image_url,
                    download_status="pending",
                )
                session.add(img)
                session.flush()
                image_rows += 1

                if download_images:
                    try:
                        local_path, content_hash = download_to_cache(
                            url=image_url,
                            cache_dir=settings.image_cache_dir,
                            timeout_ms=settings.image_download_timeout_ms,
                        )
                        img.local_path = local_path
                        img.content_hash = content_hash
                        img.download_status = "succeeded"
                        img.downloaded_at = _now()
                        downloaded += 1
                    except Exception as exc:  # noqa: BLE001
                        img.download_status = "failed"
                        img.error_json = {"message": str(exc)}

            if index % 5 == 0 or index == total_records:
                emit_progress(index, total_records, unit="listings")
                publish_step_progress(session, step, index, total_records, unit="listings")

        if download_images and image_rows:
            emit_progress(downloaded, image_rows, unit="images")
            publish_step_progress(session, step, downloaded, image_rows, unit="images")

        step.status = "succeeded"
        step.finished_at = _now()
        step.metrics_json = {
            "records_seen": len(records),
            "listings_inserted": inserted,
            "listings_updated": updated,
            "listings_skipped_existing": skipped_existing,
            "image_rows_inserted": image_rows,
            "images_downloaded": downloaded,
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

