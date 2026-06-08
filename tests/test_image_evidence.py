from __future__ import annotations

from types import SimpleNamespace

from mtg_card_recognition.config import RecognitionSettings
from ebay_workflows.services.ev_guardrails import (
    crop_match_allowed_for_pricing,
    pricing_allowed_for_candidate,
    title_match_allowed_for_pricing,
)
from ebay_workflows.services.image_evidence import (
    apply_image_evidence_gate,
    candidate_has_image_evidence,
)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        title_match_min_score_for_pricing=0.88,
        title_match_min_score_non_mtg=0.98,
        image_evidence_min_ocr_similarity=0.65,
        image_evidence_min_faiss_score=0.65,
        card_set_symbol_min_score=0.45,
    )


def _rec_settings(**overrides: object) -> RecognitionSettings:
    base = {
        "image_cache_dir": ".",
        "image_evidence_min_ocr_similarity": 0.65,
        "image_evidence_min_faiss_score": 0.65,
        "card_set_symbol_min_score": 0.45,
    }
    base.update(overrides)
    return RecognitionSettings(**base)  # type: ignore[arg-type]


def test_bulk_lot_title_rejected_for_pricing() -> None:
    allowed, reason = title_match_allowed_for_pricing(
        "500 Time Spiral Basic Land Bulk Lot MTG Magic Cards",
        "Time Spiral",
        0.95,
        _settings(),
    )
    assert allowed is False
    assert reason == "bulk_lot_title_requires_image_evidence"


def test_ocr_evidence_alone_does_not_verify() -> None:
    evidence = {"ocr_verification": {"similarity": 0.82, "ocr_title": "Lightning Bolt"}}
    card = SimpleNamespace(name="Lightning Bolt", set_code="LEA", collector_number="161")
    ok, source = candidate_has_image_evidence(
        evidence,
        "abc-123",
        _rec_settings(),
        scryfall_card=card,
    )
    assert ok is False
    assert source is None


def test_faiss_evidence_alone_does_not_verify() -> None:
    evidence = {
        "faiss_matches": [{"scryfall_id": "abc-123", "card_name": "Lightning Bolt", "score": 0.72}]
    }
    card = SimpleNamespace(name="Lightning Bolt", set_code="LEA", collector_number="161")
    ok, source = candidate_has_image_evidence(
        evidence,
        "abc-123",
        _rec_settings(),
        scryfall_card=card,
    )
    assert ok is False
    assert source is None


def test_set_collector_zone_evidence_accepts_match() -> None:
    card = SimpleNamespace(name="Murder", set_code="MKM", collector_number="123")
    evidence = {
        "zone_evidence": {
            "zones_available": True,
            "bottom_parsed": {"set_code": "MKM", "collector_number": "123"},
            "name_ocr": "Murder",
        }
    }
    ok, source = candidate_has_image_evidence(
        evidence,
        "abc-123",
        _rec_settings(),
        scryfall_card=card,
    )
    assert ok is True
    assert source == "set_collector"


def test_set_symbol_zone_evidence_accepts_strong_match() -> None:
    card = SimpleNamespace(name="Lightning Bolt", set_code="MKM", collector_number="999")
    evidence = {
        "zone_evidence": {
            "zones_available": True,
            "set_symbol_match": {"set_code": "MKM", "score": 0.62},
            "name_ocr": "Lightning Bolt",
            "bottom_parsed": {"set_code": "MKM"},
        }
    }
    ok, source = candidate_has_image_evidence(
        evidence,
        "abc-123",
        _rec_settings(),
        scryfall_card=card,
    )
    assert ok is True
    assert source == "set_symbol"


def test_crop_match_evidence_allows_bulk_lot_pricing() -> None:
    card = SimpleNamespace(id="abc-123", name="Lightning Bolt", set_code="LEA", collector_number="1")
    match_evidence = {
        "match_method": "set_collector",
        "parsed_identifiers": {"set_code": "LEA", "collector_number": "1"},
    }
    allowed, reason = crop_match_allowed_for_pricing(
        "500 card bulk lot MTG magic",
        card.name,
        0.72,
        match_evidence,
        scryfall_id=str(card.id),
        scryfall_card=card,
        settings=_settings(),
    )
    assert allowed is True
    assert reason is None


def test_crop_match_blocks_bulk_lot_without_image_evidence() -> None:
    card = SimpleNamespace(id="abc-123", name="Lightning Bolt", set_code="LEA", collector_number="1")
    allowed, reason = crop_match_allowed_for_pricing(
        "500 card bulk lot MTG magic",
        card.name,
        0.72,
        {},
        scryfall_id=str(card.id),
        scryfall_card=card,
        settings=_settings(),
    )
    assert allowed is False
    assert reason == "bulk_lot_no_crop_image_evidence"


def test_image_verified_candidate_bypasses_title_pricing_gate() -> None:
    evidence = {
        "image_verified": True,
        "image_verification_source": "set_collector",
        "match_score": 0.5,
    }
    allowed, reason = pricing_allowed_for_candidate(
        "Some listing",
        "Lightning Bolt",
        0.5,
        evidence,
        _settings(),
    )
    assert allowed is True
    assert reason is None


def test_title_only_match_rejected_without_image_evidence() -> None:
    evidence = {"pricing_eligible": True, "cardmarket_price": {"price_amount": 5.0}}
    candidate = SimpleNamespace(
        scryfall_id="abc-123",
        scryfall_card=SimpleNamespace(name="Time Spiral", set_code="TSR", collector_number="1"),
        match_score=0.9,
        confidence_score=0.9,
        evidence_json=evidence,
    )
    verified = apply_image_evidence_gate(candidate, _rec_settings())
    assert verified is False
    assert candidate.evidence_json["image_verified"] is False
    assert candidate.evidence_json["pricing_eligible"] is False
    assert "cardmarket_price" not in candidate.evidence_json
    assert float(candidate.confidence_score) <= 0.2


def test_verified_gate_restores_pricing_eligible() -> None:
    evidence = {
        "pricing_eligible": False,
        "zone_evidence": {
            "zones_available": True,
            "bottom_parsed": {"set_code": "LEA", "collector_number": "161"},
            "name_ocr": "Lightning Bolt",
        },
    }
    candidate = SimpleNamespace(
        scryfall_id="abc-123",
        scryfall_card=SimpleNamespace(name="Lightning Bolt", set_code="LEA", collector_number="161"),
        match_score=0.9,
        confidence_score=0.4,
        evidence_json=evidence,
    )
    verified = apply_image_evidence_gate(candidate, _rec_settings())
    assert verified is True
    assert candidate.evidence_json["pricing_eligible"] is True
    assert candidate.evidence_json["image_verification_source"] == "set_collector"
