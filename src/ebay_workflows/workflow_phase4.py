from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import Listing, ListingCardCandidate, ListingScore, WorkflowRun, WorkflowStep
from .services.ev_guardrails import cap_ev_adjusted
from .services.hybrid_scoring import compute_listing_score_hybrid
from .services.progress_report import emit_progress


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_decimal(value: float | Decimal | None, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _compute_listing_score(
    candidates: list[ListingCardCandidate],
    listing: Listing,
    settings: Settings,
) -> dict[str, Any]:
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

    rank_value, ev_capped = cap_ev_adjusted(ev_adjusted, listing_cost, settings)
    explanation: dict[str, Any] = {
        "listing_cost": float(listing_cost),
        "gross_value": float(gross_value),
        "matched_cards": matched_cards,
    }
    if ev_capped:
        explanation["ev_capped"] = True
        explanation["ev_cap_multiple"] = settings.ev_max_listing_cost_multiple
    return {
        "ev_raw": ev_raw,
        "confidence_score": confidence_score,
        "risk_score": risk_score,
        "ev_adjusted": ev_adjusted,
        "rank_value": rank_value,
        "explanation": explanation,
    }


def run_phase4_ranking(session: Session, settings: Settings, *, use_hybrid: bool = False) -> str:
    scoring_version = "v2_hybrid" if use_hybrid else "v1"
    run = WorkflowRun(
        workflow_name=f"{settings.workflow_default_name}_phase4",
        status="running",
        input_config_json={"source": f"ev_ranking_{scoring_version}"},
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
        total_listings = len(listings)
        if total_listings:
            emit_progress(0, total_listings, unit="listings")

        for index, listing in enumerate(listings, start=1):
            listing_candidates = by_listing.get(listing.id, [])
            if use_hybrid:
                calc = compute_listing_score_hybrid(listing_candidates, listing, settings)
            else:
                calc = _compute_listing_score(listing_candidates, listing, settings)
            existing = session.execute(
                select(ListingScore).where(ListingScore.listing_id == listing.id)
            ).scalar_one_or_none()
            if existing:
                existing.ev_raw = calc["ev_raw"]
                existing.ev_adjusted = calc["ev_adjusted"]
                existing.confidence_score = calc["confidence_score"]
                existing.risk_score = calc["risk_score"]
                existing.rank_value = calc["rank_value"]
                existing.scoring_version = scoring_version
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
                        scoring_version=scoring_version,
                        explanation_json=calc["explanation"],
                        updated_at=_now(),
                    )
                )
            scored += 1
            if index % 10 == 0 or index == total_listings:
                emit_progress(index, total_listings, unit="listings")

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

