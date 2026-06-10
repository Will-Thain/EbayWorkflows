from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import Listing, ListingCardCandidate, ListingFavorite, ListingImage, ListingScore


def _listing_thumbnail_path(listing: Listing) -> str | None:
    images: list[ListingImage] = list(listing.images or [])
    for image in images:
        if image.download_status == "succeeded" and image.local_path:
            path = Path(image.local_path)
            if path.is_file():
                return str(path)
    return None


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
    image_verification_source: str | None = None
    verification_detection_id: str | None = None
    verification_listing_image_id: str | None = None
    thumbnail_local_path: str | None = None
    is_favorited: bool = False

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
            "image_verification_source": self.image_verification_source,
            "verification_detection_id": self.verification_detection_id,
            "verification_listing_image_id": self.verification_listing_image_id,
            "thumbnail_local_path": self.thumbnail_local_path,
            "is_favorited": self.is_favorited,
        }


def fetch_ranked_listings(
    session: Session,
    *,
    limit: int = 50,
    favorites_only: bool = False,
) -> list[RankedListingRow]:
    stmt = (
        select(Listing)
        .join(ListingScore, ListingScore.listing_id == Listing.id)
        .options(
            joinedload(Listing.score),
            joinedload(Listing.images),
            joinedload(Listing.card_candidates).joinedload(ListingCardCandidate.scryfall_card),
        )
        .order_by(ListingScore.rank_value.desc())
        .limit(limit)
    )
    if favorites_only:
        stmt = stmt.join(ListingFavorite, ListingFavorite.listing_id == Listing.id)

    rows = session.execute(stmt).unique().scalars().all()
    favorite_ids = set(session.scalars(select(ListingFavorite.listing_id)).all())

    ranked: list[RankedListingRow] = []
    for index, listing in enumerate(rows, start=1):
        score = listing.score
        if not score:
            continue

        top_candidate = None
        if listing.card_candidates:
            verified = sorted(
                (c for c in listing.card_candidates if (c.evidence_json or {}).get("image_verified")),
                key=lambda c: c.rank_position,
            )
            if verified:
                top_candidate = verified[0]

        top_name = None
        top_match = None
        verification_source = None
        verification_detection_id = None
        verification_listing_image_id = None
        if top_candidate:
            if top_candidate.scryfall_card:
                top_name = top_candidate.scryfall_card.name
            top_match = float(top_candidate.match_score)
            evidence = top_candidate.evidence_json or {}
            verification_source = evidence.get("image_verification_source")
            verification_detection_id = evidence.get("verification_detection_id")
            verification_listing_image_id = evidence.get("verification_listing_image_id")

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
                image_verification_source=verification_source,
                verification_detection_id=verification_detection_id,
                verification_listing_image_id=verification_listing_image_id,
                thumbnail_local_path=_listing_thumbnail_path(listing),
                is_favorited=listing.id in favorite_ids,
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
