from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..integrations.ebay import ListingRecord, enrich_record_description, iter_listing_pages
from ..models import Listing, ListingImage, WorkflowRun, WorkflowStep
from ..persistence.repositories import ListingRepository
from ..operations.image_cache import download_many_to_cache
from ..operations.pipeline_lock import pipeline_run_lock
from ..operations.metrics import merge_phase_counters
from ..operations.progress_report import emit_progress
from ..operations.workflow_progress import publish_step_progress
from ..operations.workflow_run import utc_now
from ..workflow_errors import fail_workflow_step


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
                description_text=item.get("description_text"),
            )
        )
    return records


def _load_queries_file(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def _iter_phase1_records(
    settings: Settings,
    *,
    query: str,
    queries: list[str] | None,
    max_pages: int,
    mock_input_file: str | None,
) -> Iterator[ListingRecord]:
    if mock_input_file:
        yield from _load_mock_listings(mock_input_file)
        return
    if not settings.enable_ebay_api:
        raise ValueError("ENABLE_EBAY_API is false. Provide --mock-input-file to run Phase 1 without eBay.")

    search_queries = queries if queries else [query]
    for search_query in search_queries:
        for page in iter_listing_pages(settings, search_query, max_pages):
            yield from page


def _should_skip_existing(existing: Listing, settings: Settings, now: datetime) -> bool:
    if not settings.phase1_skip_existing_listings:
        return False
    refresh_hours = settings.phase1_refresh_after_hours
    if refresh_hours is None or refresh_hours <= 0:
        return True
    age = now - existing.last_seen_at
    return age < timedelta(hours=refresh_hours)


def _download_image_batch(
    session: Session,
    settings: Settings,
    pending: list[tuple[ListingImage, str]],
) -> int:
    if not pending:
        return 0

    urls = [url for _, url in pending]
    download_results = download_many_to_cache(
        urls,
        settings.image_cache_dir,
        settings.image_download_timeout_ms,
        max_workers=settings.pipeline_max_download_workers,
        global_requests_per_minute=settings.global_requests_per_minute_cap,
    )
    downloaded = 0
    for img, url in pending:
        outcome = download_results.get(url)
        if isinstance(outcome, Exception):
            img.download_status = "failed"
            img.error_json = {"message": str(outcome)}
            continue
        local_path, content_hash = outcome
        img.local_path = local_path
        img.content_hash = content_hash
        img.download_status = "succeeded"
        img.downloaded_at = utc_now()
        downloaded += 1
    return downloaded


def retry_failed_image_downloads(session: Session, settings: Settings) -> dict[str, int]:
    """Re-download listing images stuck as failed or never attempted (pending)."""
    missing_rows = session.execute(
        select(ListingImage).where(ListingImage.download_status.in_(("failed", "pending")))
    ).scalars().all()
    if not missing_rows:
        return {
            "images_seen": 0,
            "images_retried": 0,
            "images_succeeded": 0,
            "images_failed": 0,
            "images_pending": 0,
        }

    failed_count = sum(1 for row in missing_rows if row.download_status == "failed")
    pending_count = sum(1 for row in missing_rows if row.download_status == "pending")

    pending: list[tuple[ListingImage, str]] = []
    for row in missing_rows:
        if not row.source_url:
            continue
        row.download_status = "pending"
        row.error_json = None
        pending.append((row, row.source_url))

    chunk_size = max(1, settings.phase1_image_download_chunk_size)
    succeeded = 0
    for start in range(0, len(pending), chunk_size):
        chunk = pending[start : start + chunk_size]
        succeeded += _download_image_batch(session, settings, chunk)
        session.commit()

    return {
        "images_seen": len(missing_rows),
        "images_failed_before": failed_count,
        "images_pending_before": pending_count,
        "images_retried": len(pending),
        "images_succeeded": succeeded,
    }


def _process_records(
    session: Session,
    settings: Settings,
    step: WorkflowStep,
    records: Iterator[ListingRecord],
    *,
    download_images: bool,
    fetch_description: bool = False,
) -> dict[str, int]:
    inserted = 0
    updated = 0
    skipped_existing = 0
    refreshed_stale = 0
    image_rows = 0
    downloaded = 0
    writes_since_commit = 0
    commit_batch = max(1, settings.phase1_commit_batch_size)
    records_seen = 0
    pending_downloads: list[tuple[ListingImage, str]] = []
    now = utc_now()

    listing_repo = ListingRepository(session)

    emit_progress(0, 0, unit="listings")
    publish_step_progress(session, step, 0, 0, unit="listings")

    for record in records:
        records_seen += 1
        existing = listing_repo.get_by_external_id(record.external_listing_id)

        if existing and _should_skip_existing(existing, settings, now):
            skipped_existing += 1
            continue

        if fetch_description:
            record = enrich_record_description(settings, record)

        outcome = listing_repo.upsert_from_record(record, now=now)
        listing = outcome.listing
        if outcome.created:
            inserted += 1
        else:
            updated += 1
            if settings.phase1_skip_existing_listings:
                refreshed_stale += 1

        writes_since_commit += 1

        for image_url in record.image_urls:
            img = listing_repo.ensure_pending_image(listing.id, image_url)
            if img is None:
                continue
            session.flush()
            image_rows += 1
            if download_images:
                pending_downloads.append((img, image_url))

        if writes_since_commit >= commit_batch:
            session.commit()
            writes_since_commit = 0

        if records_seen % 5 == 0:
            emit_progress(records_seen, records_seen, unit="listings")
            publish_step_progress(session, step, records_seen, records_seen, unit="listings")

    if download_images and pending_downloads:
        chunk_size = max(1, settings.phase1_image_download_chunk_size)
        for start in range(0, len(pending_downloads), chunk_size):
            chunk = pending_downloads[start : start + chunk_size]
            downloaded += _download_image_batch(session, settings, chunk)
            session.commit()
            emit_progress(min(start + len(chunk), len(pending_downloads)), len(pending_downloads), unit="images")
            publish_step_progress(
                session,
                step,
                min(start + len(chunk), len(pending_downloads)),
                len(pending_downloads),
                unit="images",
            )

    emit_progress(records_seen, max(records_seen, 1), unit="listings")
    publish_step_progress(session, step, records_seen, max(records_seen, 1), unit="listings")

    return {
        "records_seen": records_seen,
        "listings_inserted": inserted,
        "listings_updated": updated,
        "listings_skipped_existing": skipped_existing,
        "listings_refreshed_stale": refreshed_stale,
        "image_rows_inserted": image_rows,
        "images_downloaded": downloaded,
    }


def run_phase1(
    session: Session,
    settings: Settings,
    query: str,
    max_pages: int,
    mock_input_file: str | None,
    download_images: bool,
    *,
    queries_file: str | None = None,
) -> str:
    queries = _load_queries_file(queries_file) if queries_file else None
    lock_cm = (
        pipeline_run_lock(settings.pipeline_lock_path)
        if settings.pipeline_enforce_single_run
        else nullcontext()
    )

    with lock_cm:
        run = WorkflowRun(
            workflow_name=settings.workflow_default_name,
            status="running",
            input_config_json={
                "query": query,
                "queries_file": queries_file,
                "max_pages": max_pages,
                "mock_input_file": mock_input_file,
            },
            started_at=utc_now(),
        )
        session.add(run)
        session.flush()

        step = WorkflowStep(
            run_id=run.id,
            step_name="phase1_ingest",
            phase_number=1,
            status="running",
            started_at=utc_now(),
            attempt=1,
        )
        session.add(step)
        session.flush()

        try:
            record_iter = _iter_phase1_records(
                settings,
                query=query,
                queries=queries,
                max_pages=max_pages,
                mock_input_file=mock_input_file,
            )
            metrics = _process_records(
                session,
                settings,
                step,
                record_iter,
                download_images=download_images,
                fetch_description=mock_input_file is None and settings.enable_ebay_api,
            )
            step.status = "succeeded"
            step.finished_at = utc_now()
            step.metrics_json = merge_phase_counters(
                metrics,
                pipeline_max_download_workers=settings.pipeline_max_download_workers,
                phase1_commit_batch_size=settings.phase1_commit_batch_size,
            )
            run.status = "succeeded"
            run.finished_at = utc_now()
            session.commit()
        except Exception as exc:  # noqa: BLE001
            fail_workflow_step(session, step, run, exc)
            raise

    return str(run.id)
