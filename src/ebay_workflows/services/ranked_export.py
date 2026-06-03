from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import Listing, ListingCardCandidate, ListingScore


@dataclass(slots=True)
class RankedListingRow:
    rank: int
    listing_id: str
    title: str
    listing_url: str
    currency: str
    price_amount: float
    shipping_amount: float | None
    ev_raw: float
    ev_adjusted: float
    confidence_score: float
    risk_score: float
    rank_value: float
    scoring_version: str
    top_card_name: str | None
    top_card_match_score: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "listing_id": self.listing_id,
            "title": self.title,
            "listing_url": self.listing_url,
            "currency": self.currency,
            "price_amount": self.price_amount,
            "shipping_amount": self.shipping_amount,
            "ev_raw": self.ev_raw,
            "ev_adjusted": self.ev_adjusted,
            "confidence_score": self.confidence_score,
            "risk_score": self.risk_score,
            "rank_value": self.rank_value,
            "scoring_version": self.scoring_version,
            "top_card_name": self.top_card_name,
            "top_card_match_score": self.top_card_match_score,
        }


def fetch_ranked_listings(session: Session, *, limit: int = 50) -> list[RankedListingRow]:
    rows = (
        session.execute(
            select(Listing)
            .join(ListingScore, ListingScore.listing_id == Listing.id)
            .options(
                joinedload(Listing.score),
                joinedload(Listing.card_candidates).joinedload(ListingCardCandidate.scryfall_card),
            )
            .order_by(ListingScore.rank_value.desc())
            .limit(limit)
        )
        .unique()
        .scalars()
        .all()
    )

    ranked: list[RankedListingRow] = []
    for index, listing in enumerate(rows, start=1):
        score = listing.score
        if not score:
            continue

        top_candidate = None
        if listing.card_candidates:
            top_candidate = sorted(listing.card_candidates, key=lambda c: c.rank_position)[0]

        top_name = None
        top_match = None
        if top_candidate:
            if top_candidate.scryfall_card:
                top_name = top_candidate.scryfall_card.name
            top_match = float(top_candidate.match_score)

        ranked.append(
            RankedListingRow(
                rank=index,
                listing_id=str(listing.id),
                title=listing.title,
                listing_url=listing.listing_url,
                currency=listing.currency,
                price_amount=float(listing.price_amount),
                shipping_amount=float(listing.shipping_amount) if listing.shipping_amount is not None else None,
                ev_raw=float(score.ev_raw),
                ev_adjusted=float(score.ev_adjusted),
                confidence_score=float(score.confidence_score),
                risk_score=float(score.risk_score),
                rank_value=float(score.rank_value),
                scoring_version=score.scoring_version,
                top_card_name=top_name,
                top_card_match_score=top_match,
            )
        )

    return ranked


def write_ranked_json(rows: list[RankedListingRow], output_path: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "count": len(rows),
        "listings": [row.to_dict() for row in rows],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
