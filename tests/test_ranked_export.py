from __future__ import annotations

import json
import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ebay_workflows.models import Base, Listing, ListingCardCandidate, ListingScore, ScryfallCard
from ebay_workflows.services.ranked_export import fetch_ranked_listings, write_ranked_json


def _build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_fetch_ranked_listings_orders_by_rank_value() -> None:
    session = _build_session()
    card_id = uuid.uuid4()

    low = Listing(
        external_listing_id="low-1",
        title="Low EV listing",
        listing_url="https://example.com/low",
        currency="GBP",
        price_amount=10,
        shipping_amount=1,
        raw_payload_json={},
    )
    high = Listing(
        external_listing_id="high-1",
        title="High EV listing",
        listing_url="https://example.com/high",
        currency="GBP",
        price_amount=5,
        shipping_amount=1,
        raw_payload_json={},
    )
    session.add_all([low, high])
    session.flush()

    session.add(
        ListingScore(
            listing_id=low.id,
            ev_raw=Decimal("1"),
            ev_adjusted=Decimal("1"),
            confidence_score=Decimal("0.5"),
            risk_score=Decimal("0.5"),
            rank_value=Decimal("1"),
            scoring_version="v2_hybrid",
            explanation_json={},
        )
    )
    session.add(
        ListingScore(
            listing_id=high.id,
            ev_raw=Decimal("10"),
            ev_adjusted=Decimal("8"),
            confidence_score=Decimal("0.8"),
            risk_score=Decimal("0.2"),
            rank_value=Decimal("8"),
            scoring_version="v2_hybrid",
            explanation_json={},
        )
    )
    session.add(
        ScryfallCard(
            id=card_id,
            name="Lightning Bolt",
            raw_payload_json={},
        )
    )
    session.flush()
    session.add(
        ListingCardCandidate(
            listing_id=high.id,
            source_method="title_match",
            scryfall_id=card_id,
            match_score=0.9,
            confidence_score=0.8,
            rank_position=1,
                evidence_json={"image_verified": True},
        )
    )
    session.commit()

    rows = fetch_ranked_listings(session, limit=10)

    assert len(rows) == 2
    assert rows[0].title == "High EV listing"
    assert rows[0].top_card_name == "Lightning Bolt"
    assert rows[1].title == "Low EV listing"


def test_write_ranked_json(tmp_path) -> None:
    from ebay_workflows.services.ranked_export import RankedListingRow

    rows = [
        RankedListingRow(
            rank=1,
            listing_id="id-1",
            title="Test",
            listing_url="https://example.com",
            currency="GBP",
            price_amount=1.0,
            shipping_amount=0.5,
            ev_raw=2.0,
            ev_adjusted=1.5,
            confidence_score=0.7,
            risk_score=0.3,
            rank_value=1.5,
            scoring_version="v2_hybrid",
            top_card_name="Bolt",
            top_card_match_score=0.9,
        )
    ]
    out = tmp_path / "ranked.json"
    write_ranked_json(rows, str(out))
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert payload["listings"][0]["title"] == "Test"
