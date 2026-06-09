from __future__ import annotations

from types import SimpleNamespace

from ebay_workflows.services.image_evidence import candidate_has_image_evidence
from ebay_workflows.workflow_phase5 import _apply_region_evidence_to_candidates


def test_reprint_ocr_does_not_bleed_across_candidates() -> None:
    bolt_lea = SimpleNamespace(
        scryfall_card=SimpleNamespace(name="Lightning Bolt", set_code="LEA", collector_number="161"),
        confidence_score=0.7,
        evidence_json={},
        rank_position=1,
    )
    bolt_mkm = SimpleNamespace(
        scryfall_card=SimpleNamespace(name="Lightning Bolt", set_code="MKM", collector_number="123"),
        confidence_score=0.7,
        evidence_json={},
        rank_position=2,
    )
    settings = SimpleNamespace(
        title_match_min_score_for_pricing=0.88,
        image_evidence_min_ocr_similarity=0.65,
        image_evidence_min_faiss_score=0.55,
        card_set_symbol_min_score=0.45,
    )
    updated = _apply_region_evidence_to_candidates(
        [bolt_lea, bolt_mkm],
        listing_image_id="img-1",
        detection_id="det-1",
        region_path="/tmp/crop.jpg",
        ocr_title="Lightning Bolt",
        fields={"title": ("Lightning Bolt", 0.9)},
        zone_evidence=None,
        settings=settings,
    )
    assert updated == 0
    assert bolt_lea.evidence_json == {}
    assert bolt_mkm.evidence_json == {}


def test_faiss_score_alone_does_not_verify() -> None:
    settings = SimpleNamespace(
        image_evidence_min_ocr_similarity=0.65,
        image_evidence_min_faiss_score=0.65,
    )
    evidence = {"faiss_score": 0.72}
    ok, source = candidate_has_image_evidence(evidence, "abc-123", settings)
    assert ok is False
    assert source is None
