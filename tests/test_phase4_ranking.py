"""Minimal sqlite smoke test for Phase 4 EV ranking."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ebay_workflows.models import Base, Listing, ListingCardCandidate, ListingScore, WorkflowRun
from ebay_workflows.workflows.phase4 import run_phase4_ranking


def _build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_phase4_ranking_writes_score_for_verified_candidate() -> None:
    session = _build_session()
    card_id = uuid.uuid4()
    listing = Listing(
        external_listing_id="ebay-rank-1",
        title="Sol Ring NM",
        listing_url="https://example.com/1",
        currency="EUR",
        price_amount=5.0,
        shipping_amount=1.0,
        raw_payload_json={},
    )
    session.add(listing)
    session.flush()
    session.add(
        ListingCardCandidate(
            listing_id=listing.id,
            scryfall_id=card_id,
            source_method="title_match",
            match_score=0.95,
            confidence_score=0.9,
            rank_position=1,
            evidence_json={
                "image_verified": True,
                "cardmarket_price": {"price_amount": 12.0, "currency": "EUR"},
            },
        )
    )
    session.commit()

    settings = SimpleNamespace(
        workflow_default_name="ebay_workflows",
        base_currency="EUR",
        ev_max_listing_cost_multiple=10.0,
        title_match_min_score_for_pricing=0.88,
    )
    run_id = run_phase4_ranking(session, settings)
    session.commit()

    run = session.get(WorkflowRun, uuid.UUID(run_id))
    assert run is not None
    assert run.status == "succeeded"

    score = session.execute(
        select(ListingScore).where(ListingScore.listing_id == listing.id)
    ).scalar_one()
    assert score.scoring_version == "v1"
    assert float(score.ev_raw) == 6.0
    assert float(score.rank_value) > 0
