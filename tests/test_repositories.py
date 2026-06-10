"""Repository query helpers."""

from __future__ import annotations


import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ebay_workflows.models import Base, Listing, ListingCardCandidate
from ebay_workflows.persistence.repositories import CandidateRepository, ListingRepository


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        yield session


def test_candidate_repository_for_listing(session: Session) -> None:
    listing = Listing(
        external_listing_id="ebay-1",
        title="Lightning Bolt",
        listing_url="https://example.com/1",
        currency="GBP",
        price_amount=1.0,
    )
    session.add(listing)
    session.flush()

    session.add(
        ListingCardCandidate(
            listing_id=listing.id,
            scryfall_id=None,
            source_method="title_match",
            match_score=0.9,
            confidence_score=0.9,
            evidence_json={},
        )
    )
    session.commit()

    repo = CandidateRepository(session)
    rows = repo.for_listing(listing.id)
    assert len(rows) == 1
    assert rows[0].listing_id == listing.id


def test_listing_repository_by_ids(session: Session) -> None:
    listing = Listing(
        external_listing_id="ebay-2",
        title="Counterspell",
        listing_url="https://example.com/2",
        currency="GBP",
        price_amount=2.0,
    )
    session.add(listing)
    session.commit()

    repo = ListingRepository(session)
    assert repo.get(listing.id) is not None
    assert repo.by_ids({listing.id})[listing.id].title == "Counterspell"
    assert repo.get_by_external_id("ebay-2") is not None
    assert repo.all() == [listing]


def test_candidate_repository_grouped_and_title_match(session: Session) -> None:
    listing = Listing(
        external_listing_id="ebay-3",
        title="Bolt",
        listing_url="https://example.com/3",
        currency="GBP",
        price_amount=1.0,
    )
    session.add(listing)
    session.flush()
    session.add(
        ListingCardCandidate(
            listing_id=listing.id,
            scryfall_id=None,
            source_method="title_match",
            match_score=0.8,
            confidence_score=0.8,
            evidence_json={"listing_title": "Lightning Bolt"},
        )
    )
    session.commit()

    repo = CandidateRepository(session)
    grouped = repo.grouped_by_listing()
    assert len(grouped[listing.id]) == 1
    assert repo.title_match_listing_titles()[listing.id] == "Lightning Bolt"
