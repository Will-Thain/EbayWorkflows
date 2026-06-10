from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Listing, ListingCardCandidate, ListingScore
from ..persistence.repositories import CandidateRepository, ListingRepository, ListingScoreRepository
from ..scoring.currency import listing_total_cost_base
from ..scoring.ev_guardrails import cap_ev_adjusted
from ..scoring.hybrid_scoring import compute_listing_score_hybrid
from ..candidates.image_evidence import is_verified_candidate, select_pricing_candidate
from ..operations.metrics import merge_phase_counters
from ..operations.progress_report import emit_progress
from ..operations.workflow_progress import publish_step_progress
from ..operations.workflow_run import begin_phase_run, utc_now
from ..workflow_errors import fail_workflow_step


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
        listing_cost = listing_total_cost_base(listing, settings)
        return {
            "ev_raw": -listing_cost,
            "confidence_score": Decimal("0"),
            "risk_score": Decimal("1"),
            "ev_adjusted": -listing_cost,
            "rank_value": -listing_cost,
            "explanation": {"reason": "no_candidates"},
        }

    gross_value = Decimal("0")
    confidence_total = Decimal("0")
    matched = 0
    matched_cards: list[dict] = []
    pricing_candidate = select_pricing_candidate(candidates)
    if pricing_candidate is not None and is_verified_candidate(pricing_candidate):
        cm = (pricing_candidate.evidence_json or {}).get("cardmarket_price")
        if cm:
            price_amount = _to_decimal(cm.get("price_amount"))
            confidence = _to_decimal(pricing_candidate.confidence_score, "0")
            gross_value = price_amount
            confidence_total = confidence
            matched = 1
            matched_cards.append(
                {
                    "scryfall_id": str(pricing_candidate.scryfall_id)
                    if pricing_candidate.scryfall_id
                    else None,
                    "price_amount": float(price_amount),
                    "confidence": float(confidence),
                }
            )

    listing_cost = listing_total_cost_base(listing, settings)
    ev_raw = gross_value - listing_cost
    confidence_score = confidence_total / Decimal(str(max(matched, 1)))
    risk_score = Decimal("1") - confidence_score
    ev_adjusted = ev_raw * confidence_score

    rank_value = ev_raw if matched == 0 else ev_adjusted
    ev_capped = False
    if matched > 0:
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
    run, step = begin_phase_run(
        session,
        workflow_default_name=settings.workflow_default_name,
        phase_number=4,
        step_name="phase4_ev_ranking",
        input_config={"source": f"ev_ranking_{scoring_version}"},
    )

    try:
        listing_repo = ListingRepository(session)
        candidate_repo = CandidateRepository(session)
        score_repo = ListingScoreRepository(session)
        listings = listing_repo.all()
        by_listing = candidate_repo.grouped_by_listing()

        scored = 0
        total_listings = len(listings)
        if total_listings:
            emit_progress(0, total_listings, unit="listings")
            publish_step_progress(session, step, 0, total_listings, unit="listings")

        skipped_lot_scores = 0
        for index, listing in enumerate(listings, start=1):
            existing = score_repo.get_for_listing(listing.id)
            if existing and existing.scoring_version == "v2_lot":
                skipped_lot_scores += 1
                continue

            listing_candidates = by_listing.get(listing.id, [])
            if use_hybrid:
                calc = compute_listing_score_hybrid(listing_candidates, listing, settings)
            else:
                calc = _compute_listing_score(listing_candidates, listing, settings)
            if existing:
                existing.ev_raw = calc["ev_raw"]
                existing.ev_adjusted = calc["ev_adjusted"]
                existing.confidence_score = calc["confidence_score"]
                existing.risk_score = calc["risk_score"]
                existing.rank_value = calc["rank_value"]
                existing.scoring_version = scoring_version
                existing.explanation_json = calc["explanation"]
                existing.updated_at = utc_now()
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
                        updated_at=utc_now(),
                    )
                )
            scored += 1
            if index % 10 == 0 or index == total_listings:
                emit_progress(index, total_listings, unit="listings")
                publish_step_progress(session, step, index, total_listings, unit="listings")

        step.status = "succeeded"
        step.finished_at = utc_now()
        step.metrics_json = merge_phase_counters(
            {},
            listings_seen=len(listings),
            scores_written=scored,
            skipped_lot_scores=skipped_lot_scores,
        )
        run.status = "succeeded"
        run.finished_at = utc_now()
        session.commit()
    except Exception as exc:  # noqa: BLE001
        fail_workflow_step(session, step, run, exc)
        raise

    return str(run.id)

