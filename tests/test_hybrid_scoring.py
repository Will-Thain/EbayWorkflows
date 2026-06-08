from __future__ import annotations

from types import SimpleNamespace

from ebay_workflows.services.hybrid_scoring import (
    composite_hybrid_confidence,
    compute_listing_score_hybrid,
    hybrid_confidence_components,
)


def test_hybrid_confidence_components_blend_signals() -> None:
    candidate = SimpleNamespace(
        match_score=0.9,
        scryfall_id="11111111-1111-1111-1111-111111111111",
        evidence_json={
            "image_verified": True,
            "ocr_verification": {"similarity": 0.85},
            "faiss_matches": [
                {"scryfall_id": "11111111-1111-1111-1111-111111111111", "score": 0.92}
            ],
            "cardmarket_price": {"price_amount": 2.5},
        },
    )
    components = hybrid_confidence_components(candidate)
    score = composite_hybrid_confidence(components)

    assert components["title_match_confidence"] == 0.9
    assert components["ocr_confidence"] == 0.85
    assert components["embedding_match_confidence"] == 0.92
    assert components["price_freshness_confidence"] == 1.0
    assert score > 0.85


def test_embedding_disagreement_reduces_embedding_component() -> None:
    candidate = SimpleNamespace(
        match_score=0.7,
        scryfall_id="11111111-1111-1111-1111-111111111111",
        evidence_json={
            "image_verified": True,
            "faiss_matches": [{"scryfall_id": "22222222-2222-2222-2222-222222222222", "score": 0.8}]
        },
    )
    components = hybrid_confidence_components(candidate)
    assert components["embedding_match_confidence"] == 0.4


def test_unpriced_listing_ranks_by_ev_raw_not_zero() -> None:
    listing = SimpleNamespace(price_amount=10, shipping_amount=2)
    candidate = SimpleNamespace(
        rank_position=1,
        match_score=0.85,
        scryfall_id="11111111-1111-1111-1111-111111111111",
        confidence_score=0.85,
        evidence_json={"ocr_verification": {"similarity": 0.8}},
    )
    result = compute_listing_score_hybrid([candidate], listing, settings=None)
    assert result["ev_adjusted"] == 0
    assert result["rank_value"] == -12
