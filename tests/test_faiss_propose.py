from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from ebay_workflows.services.embedding_index import EmbeddingMatch, propose_embedding_candidates


def test_propose_embedding_inserts_when_missing_from_title_matches() -> None:
    listing_id = uuid.uuid4()
    card_id = uuid.uuid4()
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=card_id, name="Bolt")
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


def test_propose_embedding_skips_existing_candidate() -> None:
    listing_id = uuid.uuid4()
    card_id = uuid.uuid4()
    session = MagicMock()
    existing = SimpleNamespace(scryfall_id=card_id, rank_position=1)
    settings = SimpleNamespace(
        faiss_propose_candidates=True,
        image_evidence_min_faiss_score=0.55,
    )
    matches = [EmbeddingMatch(scryfall_id=str(card_id), card_name="Bolt", score=0.72)]

    added = propose_embedding_candidates(session, listing_id, [existing], matches, settings)

    assert added == 0
