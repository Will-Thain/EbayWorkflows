from __future__ import annotations

from types import SimpleNamespace

from ebay_workflows.recognition.embedding_index import EmbeddingMatch, apply_embedding_evidence


def test_apply_embedding_evidence_marks_agreement() -> None:
    candidate_match = SimpleNamespace(
        scryfall_id="11111111-1111-1111-1111-111111111111",
        confidence_score=0.7,
        evidence_json={},
    )
    candidate_other = SimpleNamespace(
        scryfall_id="22222222-2222-2222-2222-222222222222",
        confidence_score=0.7,
        evidence_json={},
    )
    matches = [
        EmbeddingMatch(
            scryfall_id="11111111-1111-1111-1111-111111111111",
            card_name="Lightning Bolt",
            score=0.91,
        )
    ]

    updated = apply_embedding_evidence([candidate_match, candidate_other], matches)

    assert updated == 1
    assert candidate_match.confidence_score > 0.7
    assert candidate_match.evidence_json["embedding_agreement"] is True
    assert candidate_match.evidence_json["faiss_score"] == 0.91
    assert "faiss_matches" not in candidate_other.evidence_json
