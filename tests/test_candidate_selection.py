from __future__ import annotations

import uuid
from types import SimpleNamespace

from ebay_workflows.adapters.recognition_settings import coerce_recognition_settings
from ebay_workflows.candidates.candidate_selection import apply_per_listing_verification_gates
from ebay_workflows.config import Settings
from ebay_workflows.candidates.candidate_gate import apply_image_evidence_gate


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


def _candidate(
    *,
    listing_id: uuid.UUID,
    rank: int,
    scryfall_id: str,
    card_name: str = "Sol Ring",
    evidence: dict,
) -> SimpleNamespace:
    return SimpleNamespace(
        listing_id=listing_id,
        rank_position=rank,
        scryfall_id=scryfall_id,
        scryfall_card=SimpleNamespace(
            id=scryfall_id,
            name=card_name,
            set_code="lea",
            collector_number="1",
        ),
        match_score=0.9 - rank * 0.01,
        confidence_score=0.9,
        evidence_json=dict(evidence),
    )


def test_single_verified_winner_per_listing() -> None:
    settings = _recognition()
    listing_id = uuid.uuid4()
    verified = _candidate(
        listing_id=listing_id,
        rank=1,
        scryfall_id="card-a",
        evidence={
            "gate_status": "verified",
            "pricing_eligible": True,
            "verification_source": "set_collector",
            "zone_evidence": {"bottom_parsed": {"set_code": "lea", "collector_number": "1"}},
        },
    )
    runner_up = _candidate(
        listing_id=listing_id,
        rank=2,
        scryfall_id="card-b",
        evidence={
            "gate_status": "verified",
            "pricing_eligible": True,
            "verification_source": "set_collector",
            "zone_evidence": {"bottom_parsed": {"set_code": "lea", "collector_number": "1"}},
        },
    )

    verified_count, gated = apply_per_listing_verification_gates(
        [verified, runner_up],
        settings,
    )

    assert verified_count == 1
    assert gated == 1
    assert verified.evidence_json.get("image_verified") is True
    assert runner_up.evidence_json.get("image_verified") is False


def test_apply_image_evidence_gate_demotes_non_set_collector() -> None:
    settings = _recognition()
    candidate = SimpleNamespace(
        scryfall_id="card-1",
        scryfall_card=SimpleNamespace(id="card-1", set_code="lea", collector_number="1", name="Sol Ring"),
        confidence_score=0.9,
        evidence_json={
            "gate_status": "verified",
            "pricing_eligible": True,
            "verification_source": "set_symbol",
            "zone_evidence": {
                "bottom_parsed": {"set_code": "lea", "collector_number": "1"},
                "symbol_match": {"set_code": "lea", "score": 0.99},
            },
        },
    )
    assert apply_image_evidence_gate(candidate, settings) is False
    assert candidate.evidence_json.get("pricing_eligible") is False
