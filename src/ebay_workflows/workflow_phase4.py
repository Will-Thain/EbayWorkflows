from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import Listing, ListingCardCandidate, ListingScore, WorkflowRun, WorkflowStep


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_decimal(value: float | Decimal | None, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _compute_listing_score(candidates: list[ListingCardCandidate], listing: Listing) -> dict:
    if not candidates:
        listing_cost = _to_decimal(listing.price_amount) + _to_decimal(listing.shipping_amount)
        return {
            "ev_raw": -listing_cost,
            "confidence_score": Decimal("0"),
            "risk_score": Decimal("1"),
            "ev_adjusted": -listing_cost,
            "rank_value": -listing_cost,
            "explanation": {"reason": "no_candidates"},
        }

    top = sorted(candidates, key=lambda c: c.rank_position)[:3]
    gross_value = Decimal("0")
    confidence_total = Decimal("0")
    matched = 0
    matched_cards: list[dict] = []
    for candidate in top:
        cm = (candidate.evidence_json or {}).get("cardmarket_price")
        if not cm:
            continue
        price_amount = _to_decimal(cm.get("price_amount"))
        confidence = _to_decimal(candidate.confidence_score, "0")
        gross_value += price_amount
        confidence_total += confidence
        matched += 1
        matched_cards.append(
            {
                "scryfall_id": str(candidate.scryfall_id) if candidate.scryfall_id else None,
                "price_amount": float(price_amount),
                "confidence": float(confidence),
            }
        )

    listing_cost = _to_decimal(listing.price_amount) + _to_decimal(listing.shipping_amount)
    ev_raw = gross_value - listing_cost
    confidence_score = confidence_total / Decimal(str(max(matched, 1)))
    risk_score = Decimal("1") - confidence_score
    ev_adjusted = ev_raw * confidence_score

    return {
        "ev_raw": ev_raw,
        "confidence_score": confidence_score,
        "risk_score": risk_score,
        "ev_adjusted": ev_adjusted,
        "rank_value": ev_adjusted,
        "explanation": {
            "listing_cost": float(listing_cost),
            "gross_value": float(gross_value),
            "matched_cards": matched_cards,
        },
    }


def run_phase4_ranking(session: Session, settings: Settings) -> str:
    run = WorkflowRun(
        workflow_name=f"{settings.workflow_default_name}_phase4",
        status="running",
        input_config_json={"source": "ev_ranking_v1"},
        started_at=_now(),
    )
    session.add(run)
    session.flush()

    step = WorkflowStep(
        run_id=run.id,
        step_name="phase4_ev_ranking",
        phase_number=4,
        status="running",
        attempt=1,
        started_at=_now(),
    )
    session.add(step)
    session.flush()

    try:
        listings = session.execute(select(Listing)).scalars().all()
        candidate_rows = session.execute(select(ListingCardCandidate)).scalars().all()
        by_listing: dict[uuid.UUID, list[ListingCardCandidate]] = {}
        for row in candidate_rows:
            by_listing.setdefault(row.listing_id, []).append(row)

        scored = 0
        for listing in listings:
            calc = _compute_listing_score(by_listing.get(listing.id, []), listing)
            existing = session.execute(
                select(ListingScore).where(ListingScore.listing_id == listing.id)
            ).scalar_one_or_none()
            if existing:
                existing.ev_raw = calc["ev_raw"]
                existing.ev_adjusted = calc["ev_adjusted"]
                existing.confidence_score = calc["confidence_score"]
                existing.risk_score = calc["risk_score"]
                existing.rank_value = calc["rank_value"]
                existing.scoring_version = "v1"
                existing.explanation_json = calc["explanation"]
                existing.updated_at = _now()
            else:
                session.add(
                    ListingScore(
                        listing_id=listing.id,
                        ev_raw=calc["ev_raw"],
                        ev_adjusted=calc["ev_adjusted"],
                        confidence_score=calc["confidence_score"],
                        risk_score=calc["risk_score"],
                        rank_value=calc["rank_value"],
                        scoring_version="v1",
                        explanation_json=calc["explanation"],
                        updated_at=_now(),
                    )
                )
            scored += 1

        step.status = "succeeded"
        step.finished_at = _now()
        step.metrics_json = {"listings_seen": len(listings), "scores_written": scored}
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

