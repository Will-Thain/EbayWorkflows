from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Listing, ListingCardCandidate, ListingScore


def collect_match_stats(session: Session) -> dict[str, Any]:
    """Snapshot verification and pricing stats for operator dashboards."""
    total_listings = int(session.execute(select(func.count()).select_from(Listing)).scalar_one())
    total_candidates = int(
        session.execute(select(func.count()).select_from(ListingCardCandidate)).scalar_one()
    )
    scored_listings = int(
        session.execute(select(func.count()).select_from(ListingScore)).scalar_one()
    )

    verified_evidence = session.execute(
        select(ListingCardCandidate.evidence_json).where(
            ListingCardCandidate.evidence_json["image_verified"].as_boolean().is_(True)
        )
    ).scalars()

    source_counts: dict[str, int] = {}
    verified_candidates = 0
    for evidence in verified_evidence:
        if not evidence or not evidence.get("image_verified"):
            continue
        verified_candidates += 1
        key = str(evidence.get("image_verification_source") or "unknown")
        source_counts[key] = source_counts.get(key, 0) + 1

    verified_listings = int(
        session.execute(
            select(func.count(func.distinct(ListingCardCandidate.listing_id)))
            .where(ListingCardCandidate.evidence_json["image_verified"].as_boolean().is_(True))
        ).scalar_one()
    )

    pricing_eligible = int(
        session.execute(
            select(func.count())
            .select_from(ListingCardCandidate)
            .where(ListingCardCandidate.evidence_json["pricing_eligible"].as_boolean().is_(True))
        ).scalar_one()
    )

    positive_rank = int(
        session.execute(
            select(func.count()).select_from(ListingScore).where(ListingScore.rank_value > 0)
        ).scalar_one()
    )

    return {
        "total_listings": total_listings,
        "total_candidates": total_candidates,
        "scored_listings": scored_listings,
        "verified_listings": verified_listings,
        "verified_candidates": verified_candidates,
        "verification_source_counts": source_counts,
        "pricing_eligible_candidates": pricing_eligible,
        "listings_with_positive_rank": positive_rank,
    }
