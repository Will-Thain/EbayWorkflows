from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ebay_workflows.models import Base, Listing, ListingCardCandidate, ListingScore
from ebay_workflows.services.match_stats import collect_match_stats


@pytest.fixture()
def stats_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def test_collect_match_stats_empty(stats_session: Session) -> None:
    stats = collect_match_stats(stats_session)
    assert stats["total_listings"] == 0
    assert stats["verified_listings"] == 0
    assert stats["verification_source_counts"] == {}


def test_collect_match_stats_verified_sqlite(stats_session: Session) -> None:
    listing_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    stats_session.add(
        Listing(
            id=listing_id,
            external_listing_id="ebay-1",
            title="Lightning Bolt",
            listing_url="https://example.com",
            currency="EUR",
            price_amount=10.0,
            raw_payload_json={},
            first_seen_at=now,
            last_seen_at=now,
        )
    )
    stats_session.add(
        ListingCardCandidate(
            listing_id=listing_id,
            source_method="title_match",
            scryfall_id=uuid.uuid4(),
            match_score=0.9,
            confidence_score=0.9,
            rank_position=1,
            evidence_json={
                "image_verified": True,
                "image_verification_source": "set_collector",
                "pricing_eligible": True,
            },
        )
    )
    stats_session.add(
        ListingScore(
            listing_id=listing_id,
            ev_raw=5.0,
            ev_adjusted=4.0,
            confidence_score=0.8,
            risk_score=0.2,
            rank_value=4.0,
            scoring_version="v2_hybrid",
            explanation_json={},
        )
    )
    stats_session.commit()

    stats = collect_match_stats(stats_session)
    assert stats["verified_listings"] == 1
    assert stats["verification_source_counts"]["set_collector"] == 1
    assert stats["pricing_eligible_candidates"] == 1
    assert stats["listings_with_positive_rank"] == 1
