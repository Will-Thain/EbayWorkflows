from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import Settings
from .models import Listing, ListingCardCandidate, ScryfallCard, WorkflowRun, WorkflowStep
from .services.ev_guardrails import title_match_allowed_for_pricing
from .services.progress_report import emit_progress
from .services.workflow_progress import publish_step_progress


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


def _best_matches(title: str, cards: list[ScryfallCard], top_k: int) -> list[tuple[ScryfallCard, float]]:
    scored: list[tuple[ScryfallCard, float]] = []
    for card in cards:
        ratio = fuzz.WRatio(title.lower(), card.name.lower())
        score = ratio / 100.0
        if score >= 0.55:
            scored.append((card, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


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
        listings = session.execute(select(Listing)).scalars().all()
        cards = session.execute(select(ScryfallCard)).scalars().all()
        if not cards:
            raise ValueError("No Scryfall cards loaded. Run sync and load first.")

        matched_listings = 0
        candidate_rows = 0
        total_listings = len(listings)
        if total_listings:
            emit_progress(0, total_listings, unit="listings")
            publish_step_progress(session, step, 0, total_listings, unit="listings")

        for index, listing in enumerate(listings, start=1):
            session.execute(delete(ListingCardCandidate).where(ListingCardCandidate.listing_id == listing.id))
            matches = _best_matches(listing.title, cards, top_k=top_k)
            rank = 1
            for card, score in matches:
                pricing_ok, reject_reason = title_match_allowed_for_pricing(
                    listing.title, card.name, score, settings
                )
                evidence = {
                    "listing_title": listing.title,
                    "matched_card_name": card.name,
                    "method": "rapidfuzz_wratio",
                    "pricing_eligible": pricing_ok,
                }
                if reject_reason:
                    evidence["pricing_reject_reason"] = reject_reason
                session.add(
                    ListingCardCandidate(
                        listing_id=listing.id,
                        source_method="title_match",
                        scryfall_id=card.id,
                        match_score=score,
                        confidence_score=score if pricing_ok else min(score, 0.5),
                        rank_position=rank,
                        evidence_json=evidence,
                    )
                )
                rank += 1
                candidate_rows += 1
            if matches:
                matched_listings += 1

            if index % 3 == 0 or index == total_listings:
                emit_progress(index, total_listings, unit="listings")
                publish_step_progress(session, step, index, total_listings, unit="listings")

        step.status = "succeeded"
        step.finished_at = _now()
        step.metrics_json = {
            "listings_seen": len(listings),
            "listings_matched": matched_listings,
            "candidate_rows_created": candidate_rows,
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

