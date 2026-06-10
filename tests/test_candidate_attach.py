from __future__ import annotations

import uuid
from types import SimpleNamespace

from ebay_workflows.candidates.candidate_attach import (
    candidates_for_region_evidence,
    merge_verification_provenance,
)


def test_merge_verification_provenance_idempotent() -> None:
    evidence = merge_verification_provenance(
        {"ocr_verification": {"ocr_title": "Bolt"}},
        listing_image_id="img-1",
        detection_id="det-1",
        region_path="/tmp/crop.png",
    )
    again = merge_verification_provenance(
        evidence,
        listing_image_id="img-2",
        detection_id="det-2",
        region_path="/tmp/other.png",
    )
    assert again["verification_listing_image_id"] == "img-2"
    assert again["verification_detection_id"] == "det-2"
    assert again["ocr_verification"]["ocr_title"] == "Bolt"


def test_candidates_for_region_evidence_matches_set_collector() -> None:
    card_id = uuid.uuid4()
    candidate = SimpleNamespace(
        scryfall_id=card_id,
        scryfall_card=SimpleNamespace(set_code="lea", collector_number="1", name="Sol Ring"),
    )
    matches = candidates_for_region_evidence(
        [candidate],
        ocr_title=None,
        fields={},
        zone_evidence={"bottom_parsed": {"set_code": "lea", "collector_number": "1"}},
    )
    assert matches == [candidate]


def test_candidates_for_region_evidence_rejects_mismatch() -> None:
    candidate = SimpleNamespace(
        scryfall_id=uuid.uuid4(),
        scryfall_card=SimpleNamespace(set_code="lea", collector_number="1", name="Sol Ring"),
    )
    matches = candidates_for_region_evidence(
        [candidate],
        ocr_title=None,
        fields={},
        zone_evidence={"bottom_parsed": {"set_code": "lea", "collector_number": "999"}},
    )
    assert matches == []
