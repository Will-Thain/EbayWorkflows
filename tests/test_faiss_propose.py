from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from ebay_workflows.models import Base, Listing, ListingCardCandidate, ScryfallCard
from ebay_workflows.services.embedding_index import EmbeddingMatch, propose_embedding_candidates


def test_propose_embedding_inserts_when_missing_from_title_matches() -> None:
    listing_id = uuid.uuid4()
    card_id = uuid.uuid4()
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=card_id, name="Bolt")
    session.execute.return_value.first.return_value = None
    candidates: list[SimpleNamespace] = []
    settings = SimpleNamespace(
        faiss_propose_candidates=True,
        image_evidence_min_faiss_score=0.55,
    )
    matches = [EmbeddingMatch(scryfall_id=str(card_id), card_name="Bolt", score=0.72)]

    added = propose_embedding_candidates(session, listing_id, candidates, matches, settings)

    assert added == 1
    assert len(candidates) == 1
    assert candidates[0].source_method == "faiss_proposal"
    assert str(candidates[0].scryfall_id) == str(card_id)
    session.flush.assert_called_once()


def test_propose_embedding_skips_existing_candidate() -> None:
    listing_id = uuid.uuid4()
    card_id = uuid.uuid4()
    session = MagicMock()
    session.execute.return_value.first.return_value = None
    existing = SimpleNamespace(scryfall_id=card_id, rank_position=1)
    settings = SimpleNamespace(
        faiss_propose_candidates=True,
        image_evidence_min_faiss_score=0.55,
    )
    matches = [EmbeddingMatch(scryfall_id=str(card_id), card_name="Bolt", score=0.72)]

    added = propose_embedding_candidates(session, listing_id, [existing], matches, settings)

    assert added == 0
    session.flush.assert_not_called()


@pytest.fixture()
def faiss_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def test_propose_embedding_skips_duplicate_when_listing_reloads_candidates(faiss_session: Session) -> None:
    """Simulate a second listing image re-querying candidates after the first proposal flushed."""
    listing_id = uuid.uuid4()
    card_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    faiss_session.add(
        Listing(
            id=listing_id,
            external_listing_id="ebay-dup",
            title="Dual image listing",
            listing_url="https://example.com",
            currency="EUR",
            price_amount=5.0,
            raw_payload_json={},
            first_seen_at=now,
            last_seen_at=now,
        )
    )
    faiss_session.add(
        ScryfallCard(
            id=card_id,
            name="Lightning Bolt",
            raw_payload_json={},
            updated_at=now,
        )
    )
    faiss_session.commit()

    settings = SimpleNamespace(
        faiss_propose_candidates=True,
        image_evidence_min_faiss_score=0.55,
    )
    matches = [EmbeddingMatch(scryfall_id=str(card_id), card_name="Lightning Bolt", score=0.72)]

    first_candidates: list[ListingCardCandidate] = []
    assert propose_embedding_candidates(faiss_session, listing_id, first_candidates, matches, settings) == 1

    second_candidates: list[ListingCardCandidate] = []
    assert propose_embedding_candidates(faiss_session, listing_id, second_candidates, matches, settings) == 0

    count = faiss_session.execute(
        select(func.count())
        .select_from(ListingCardCandidate)
        .where(
            ListingCardCandidate.listing_id == listing_id,
            ListingCardCandidate.source_method == "faiss_proposal",
        )
    ).scalar_one()
    assert count == 1
