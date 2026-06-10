from __future__ import annotations

from types import SimpleNamespace

from ebay_workflows.adapters.recognition_settings import coerce_recognition_settings
from ebay_workflows.config import Settings
from ebay_workflows.services.candidate_gate import (
    apply_image_evidence_gate,
    evaluate_image_verification,
)


def _recognition() -> object:
    return coerce_recognition_settings(
        Settings(
            DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ebay_workflows",
            SCRYFALL_BULK_URI="https://api.scryfall.com/bulk-data/default-cards",
            CARDMARKET_BULK_FILE_PATH="./samples/cardmarket_prices.csv",
            IMAGE_CACHE_DIR="./.cache/images",
            FAISS_INDEX_PATH="./.cache/faiss/index.bin",
            GLOBAL_REQUESTS_PER_MINUTE_CAP="90",
            ENABLE_EBAY_API="false",
            DISABLE_LIVE_API_WRITES="true",
        )
    )


def _card(*, set_code: str = "lea", collector: str = "1", name: str = "Sol Ring") -> SimpleNamespace:
    return SimpleNamespace(id="card-1", set_code=set_code, collector_number=collector, name=name)


def test_set_symbol_only_does_not_verify() -> None:
    settings = _recognition()
    card = _card(set_code="prm", name="Flooded Strand")
    evidence = {
        "zone_evidence": {
            "bottom_parsed": {"set_code": "prm"},
            "symbol_match": {"set_code": "prm", "score": 0.99},
            "name_ocr": "OO",
        }
    }
    verified, source, _ = evaluate_image_verification(
        evidence,
        "card-1",
        settings,
        scryfall_card=card,
    )
    assert verified is False
    assert source is None


def test_cascade_blocked_not_upgraded_by_legacy_heuristics() -> None:
    settings = _recognition()
    card = _card()
    evidence = {
        "gate_status": "blocked_at_gate",
        "pricing_eligible": False,
        "gate_fail_reason": "symbol_only",
        "zone_evidence": {
            "bottom_parsed": {"set_code": "lea", "collector_number": "1"},
            "symbol_match": {"set_code": "lea", "score": 0.99},
            "name_ocr": "Sol Ring",
        },
    }
    verified, source, _ = evaluate_image_verification(
        evidence,
        "card-1",
        settings,
        scryfall_card=card,
    )
    assert verified is False
    assert source is None


def test_cascade_verified_set_collector_honored() -> None:
    settings = _recognition()
    card = _card()
    evidence = {
        "gate_status": "verified",
        "pricing_eligible": True,
        "verification_source": "set_collector",
        "zone_evidence": {"bottom_parsed": {"set_code": "lea", "collector_number": "1"}},
    }
    verified, source, strength = evaluate_image_verification(
        evidence,
        "card-1",
        settings,
        scryfall_card=card,
    )
    assert verified is True
    assert source == "set_collector"
    assert strength == 30


def test_apply_image_evidence_gate_prices_only_set_collector() -> None:
    settings = _recognition()
    candidate = SimpleNamespace(
        scryfall_id="card-1",
        scryfall_card=_card(),
        confidence_score=0.9,
        evidence_json={
            "gate_status": "verified",
            "pricing_eligible": True,
            "verification_source": "set_collector",
            "zone_evidence": {
                "bottom_parsed": {"set_code": "lea", "collector_number": "1"},
                "name_ocr": "Sol Ring",
            },
        },
    )
    assert apply_image_evidence_gate(candidate, settings) is True
    assert candidate.evidence_json["pricing_eligible"] is True
    assert candidate.evidence_json["image_verification_source"] == "set_collector"
