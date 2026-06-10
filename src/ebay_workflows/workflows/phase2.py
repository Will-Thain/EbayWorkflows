from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Listing, ListingCardCandidate, ScryfallCard, WorkflowRun, WorkflowStep
from ..persistence.repositories import CandidateRepository
from ..scoring.ev_guardrails import title_match_allowed_for_pricing
from ..operations.match_event_log import log_positive_match, match_log_path
from ..operations.listing_filters import is_bulk_lot_title
from ..operations.progress_report import emit_progress
from ..operations.metrics import merge_phase_counters
from ..operations.workflow_sample import fetch_limited_listings
from ..recognition import (
    CardMatchEntry,
    ScryfallTitleIndex,
    TitleMatchResult,
    build_set_collector_index,
    match_listings_parallel,
)
from ..operations.workflow_progress import publish_step_progress
from ..workflow_errors import fail_workflow_step


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def upsert_scryfall_cards(session: Session, cards: list[dict[str, Any]]) -> int:
    inserted_or_updated = 0
    for card in cards:
        card_id = _as_uuid(card.get("id"))
        if card_id is None:
            continue
        existing = session.get(ScryfallCard, card_id)
        image_uris = card.get("image_uris") or {}
        fields = {
            "name": card.get("name", ""),
            "oracle_id": _as_uuid(card.get("oracle_id")),
            "set_code": card.get("set"),
            "collector_number": card.get("collector_number"),
            "lang": card.get("lang"),
            "released_at": card.get("released_at"),
            "image_normal": image_uris.get("normal"),
            "image_small": image_uris.get("small"),
            "raw_payload_json": card,
            "updated_at": _now(),
        }

        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
        else:
            session.add(ScryfallCard(id=card_id, **fields))
        inserted_or_updated += 1
    session.commit()
    return inserted_or_updated


def load_cards_from_cache(settings: Settings) -> list[dict[str, Any]]:
    path = Path(settings.scryfall_bulk_cache_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Scryfall cache file not found at {path}. Run sync-scryfall first."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Cached Scryfall file is not a list.")
    return data


def _listing_ids_with_current_title_matches(session: Session) -> dict[uuid.UUID, str]:
    """Map listing_id -> title stored on existing title_match evidence."""
    return CandidateRepository(session).title_match_listing_titles()


def _persist_matches(
    session: Session,
    listing: Listing,
    matches: list[TitleMatchResult],
    settings: Settings,
) -> tuple[int, bool]:
    session.execute(delete(ListingCardCandidate).where(ListingCardCandidate.listing_id == listing.id))
    if not matches:
        return 0, False

    if settings.phase2_skip_bulk_lot_title_match and is_bulk_lot_title(listing.title):
        return 0, False

    rank = 1
    rows_created = 0
    for match in matches:
        pricing_ok, reject_reason = title_match_allowed_for_pricing(
            listing.title, match.card_name, match.score, settings
        )
        evidence = {
            "listing_title": listing.title,
            "matched_card_name": match.card_name,
            "method": match.match_method,
            "pricing_eligible": pricing_ok,
        }
        if reject_reason:
            evidence["pricing_reject_reason"] = reject_reason
        session.add(
            ListingCardCandidate(
                listing_id=listing.id,
                source_method="title_match",
                scryfall_id=_as_uuid(match.card_id),
                match_score=match.score,
                confidence_score=match.score if pricing_ok else min(match.score, 0.5),
                rank_position=rank,
                evidence_json=evidence,
            )
        )
        log_positive_match(
            event="title_match",
            phase=2,
            listing_id=str(listing.id),
            external_listing_id=listing.external_listing_id,
            scryfall_id=match.card_id,
            card_name=match.card_name,
            match_score=float(match.score),
            source_method="title_match",
            match_method=match.match_method,
            pricing_eligible=pricing_ok,
            pricing_reject_reason=reject_reason,
            log_path=match_log_path(settings),
        )
        rank += 1
        rows_created += 1
    return rows_created, True


def run_phase2_title_match(
    session: Session,
    settings: Settings,
    top_k: int = 3,
) -> str:
    run = WorkflowRun(
        workflow_name=f"{settings.workflow_default_name}_phase2",
        status="running",
        input_config_json={"top_k": top_k, "source": "title_match"},
        started_at=_now(),
    )
    session.add(run)
    session.flush()

    step = WorkflowStep(
        run_id=run.id,
        step_name="phase2_title_match",
        phase_number=2,
        status="running",
        attempt=1,
        started_at=_now(),
    )
    session.add(step)
    session.flush()

    try:
        listings = fetch_limited_listings(session, settings)
        card_rows = session.execute(
            select(
                ScryfallCard.id,
                ScryfallCard.name,
                ScryfallCard.set_code,
                ScryfallCard.collector_number,
            )
        ).all()
        if not card_rows:
            raise ValueError("No Scryfall cards loaded. Run sync and load first.")

        card_by_id = {
            str(card_id): SimpleNamespace(name=name)
            for card_id, name, _, _ in card_rows
        }
        listing_by_id = {listing.id: listing for listing in listings}
        stored_titles = _listing_ids_with_current_title_matches(session) if settings.phase2_skip_unchanged_listings else {}

        to_match: list[tuple[str, str]] = []
        skipped_listings = 0
        for listing in listings:
            if stored_titles.get(listing.id) == listing.title:
                skipped_listings += 1
                continue
            to_match.append((str(listing.id), listing.title))

        index = ScryfallTitleIndex.from_entries(
            [
                CardMatchEntry(
                    card_id=str(card_id),
                    name=name,
                    set_code=set_code,
                    collector_number=collector_number,
                )
                for card_id, name, set_code, collector_number in card_rows
            ]
        )
        set_collector_index = build_set_collector_index(
            [
                (str(card_id), set_code, collector_number)
                for card_id, _, set_code, collector_number in card_rows
            ]
        )
        scryfall_lookup = card_by_id
        match_results = match_listings_parallel(
            to_match,
            index,
            top_k=top_k,
            prefilter_size=settings.title_match_prefilter_size,
            max_workers=settings.pipeline_max_title_match_workers,
            score_cutoff=settings.title_match_score_cutoff,
            set_collector_index=set_collector_index,
            card_by_id=scryfall_lookup,
        )

        matched_listings = 0
        candidate_rows = 0
        total_listings = len(listings)
        processed = skipped_listings

        if total_listings:
            emit_progress(processed, total_listings, unit="listings")
            publish_step_progress(session, step, processed, total_listings, unit="listings")

        for listing_id_str, matches in match_results.items():
            listing = listing_by_id.get(uuid.UUID(listing_id_str))
            if listing is None:
                continue
            rows_created, had_matches = _persist_matches(session, listing, matches, settings)
            candidate_rows += rows_created
            if had_matches:
                matched_listings += 1
            processed += 1
            if processed % 3 == 0 or processed == total_listings:
                emit_progress(processed, total_listings, unit="listings")
                publish_step_progress(session, step, processed, total_listings, unit="listings")

        if processed != total_listings:
            emit_progress(total_listings, total_listings, unit="listings")
            publish_step_progress(session, step, total_listings, total_listings, unit="listings")

        step.status = "succeeded"
        step.finished_at = _now()
        step.metrics_json = merge_phase_counters(
            {},
            listings_seen=len(listings),
            listings_matched=matched_listings + skipped_listings,
            listings_skipped_unchanged=skipped_listings,
            listings_rematched=len(to_match),
            candidate_rows_created=candidate_rows,
            title_match_prefilter_size=settings.title_match_prefilter_size,
            title_match_score_cutoff=settings.title_match_score_cutoff,
            pipeline_max_title_match_workers=settings.pipeline_max_title_match_workers,
        )
        run.status = "succeeded"
        run.finished_at = _now()
        session.commit()
    except Exception as exc:  # noqa: BLE001
        fail_workflow_step(session, step, run, exc)
        raise

    return str(run.id)
