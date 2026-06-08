from __future__ import annotations

from types import SimpleNamespace

from ebay_workflows.services.image_evidence import candidate_has_image_evidence
from ebay_workflows.services.scryfall_mana import parse_mana_cost_string, scryfall_card_mana_colors


def test_parse_mana_cost_string() -> None:
    assert parse_mana_cost_string("{1}{R}{R}") == frozenset({"R"})
    assert parse_mana_cost_string("{W}{U}") == frozenset({"W", "U"})
    assert parse_mana_cost_string("") == frozenset()


def test_scryfall_card_mana_colors_from_payload() -> None:
    card = SimpleNamespace(
        raw_payload_json={"mana_cost": "{2}{G}", "colors": ["G"]},
    )
    assert scryfall_card_mana_colors(card) == frozenset({"G"})


def test_mana_zone_evidence_alone_does_not_verify() -> None:
    card = SimpleNamespace(raw_payload_json={"mana_cost": "{R}"})
    settings = SimpleNamespace(
        image_evidence_min_mana_confidence=0.30,
        image_evidence_min_ocr_similarity=0.60,
        image_evidence_min_faiss_score=0.55,
        card_set_symbol_min_score=0.45,
    )
    evidence = {
        "zone_evidence": {
            "mana_cost": {"colors": ["R"], "confidence": 0.5},
        }
    }
    ok, source = candidate_has_image_evidence(
        evidence,
        "abc-123",
        settings,
        scryfall_card=card,
    )
    assert ok is False
    assert source is None
