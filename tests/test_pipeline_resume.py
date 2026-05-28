from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ebay_workflows.models import Base, Listing, ListingCardCandidate, ListingScore
from ebay_workflows.pipeline_resume import _phase_completion_snapshot


def _build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_phase_completion_snapshot_empty_db() -> None:
    session = _build_session()
    snapshot = _phase_completion_snapshot(session)
    assert snapshot == {1: False, 2: False, 3: False, 4: False, 5: False, 6: False}


def test_phase_completion_snapshot_detects_progress() -> None:
    session = _build_session()
    listing = Listing(
        external_listing_id="resume-1",
        title="MTG resume lot",
        listing_url="https://example.com/r/1",
        currency="EUR",
        price_amount=10,
        shipping_amount=1,
        raw_payload_json={},
    )
    session.add(listing)
    session.flush()
    session.add(
        ListingCardCandidate(
            listing_id=listing.id,
            source_method="title_match",
            scryfall_id=None,
            match_score=0.7,
            confidence_score=0.7,
            rank_position=1,
            evidence_json={},
        )
    )
    session.add(
        ListingScore(
            listing_id=listing.id,
            ev_raw=1,
            ev_adjusted=0.5,
            confidence_score=0.5,
            risk_score=0.5,
            rank_value=0.5,
            scoring_version="v1",
            explanation_json={},
        )
    )
    session.commit()

    snapshot = _phase_completion_snapshot(session)
    assert snapshot[1] is True
    assert snapshot[2] is True
    assert snapshot[4] is True
