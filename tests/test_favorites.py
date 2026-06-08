from __future__ import annotations


from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ebay_workflows.gui import favorites as fav
from ebay_workflows.models import Base, Listing, ListingScore
from ebay_workflows.services.ranked_export import fetch_ranked_listings


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_favorite_toggle_and_filter() -> None:
    session = _session()
    listing = Listing(
        external_listing_id="fav-1",
        title="Favourite test",
        listing_url="https://example.com/fav",
        currency="GBP",
        price_amount=1,
        shipping_amount=0,
        raw_payload_json={},
    )
    session.add(listing)
    session.flush()
    session.add(
        ListingScore(
            listing_id=listing.id,
            ev_raw=5,
            ev_adjusted=4,
            confidence_score=0.5,
            risk_score=0.5,
            rank_value=4,
            scoring_version="v2_hybrid",
            explanation_json={},
        )
    )
    session.commit()

    fav.set_favorite(session, listing.id, note="watch")
    rows = fetch_ranked_listings(session, limit=10, favorites_only=True)
    assert len(rows) == 1
    assert rows[0].is_favorited
    assert rows[0].title == "Favourite test"

    fav.clear_favorite(session, listing.id)
    rows = fetch_ranked_listings(session, limit=10, favorites_only=True)
    assert len(rows) == 0
