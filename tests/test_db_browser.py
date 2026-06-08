from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ebay_workflows.gui.db_browser import run_curated_query
from ebay_workflows.models import Base, Listing, ListingFavorite, ListingScore


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_table_counts_query() -> None:
    session = _session()
    listing = Listing(
        external_listing_id="db-1",
        title="Test",
        listing_url="https://example.com",
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
            ev_raw=Decimal("1"),
            ev_adjusted=Decimal("1"),
            confidence_score=Decimal("0.5"),
            risk_score=Decimal("0.5"),
            rank_value=Decimal("1"),
            scoring_version="v2_hybrid",
            explanation_json={},
        )
    )
    session.add(ListingFavorite(listing_id=listing.id, note="watch"))
    session.commit()

    headers, rows = run_curated_query("counts", session)
    assert "listings" in [r[0] for r in rows]
    assert headers[0] == "table"

    fav_headers, fav_rows = run_curated_query("favourites", session)
    assert fav_headers[0] == "favorited_at"
    assert len(fav_rows) == 1
    assert fav_rows[0][1] == "watch"
