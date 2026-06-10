"""Integration-style tests for Phase 5 cascade attach path."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from mtg_card_recognition.cascade.models import Proposal
from mtg_card_recognition.pipeline.listing import ListingCascadeResult

from ebay_workflows.candidates.candidate_sync import apply_cascade_proposals_to_candidates


def _proposal(
    printing_id: str,
    *,
    gate_status: str = "verified",
    pricing_eligible: bool = True,
    verification_source: str = "set_collector",
) -> Proposal:
    return Proposal(
        printing_id=printing_id,
        gate_status=gate_status,
        pricing_eligible=pricing_eligible,
        verification_source=verification_source,
        image_verified=gate_status == "verified",
        corroboration_score=0.91,
    )


def test_cascade_attach_maps_regions_to_detection_ids() -> None:
    """Mirrors Phase 5 _persist_analysis cascade attach with region→detection maps."""
    card_a = uuid.uuid4()
    card_b = uuid.uuid4()
    candidate_a = SimpleNamespace(
        scryfall_id=card_a,
        confidence_score=0.4,
        evidence_json={},
    )
    candidate_b = SimpleNamespace(
        scryfall_id=card_b,
        confidence_score=0.4,
        evidence_json={},
    )
    proposal_a = _proposal(str(card_a))
    proposal_b = _proposal(str(card_b), gate_status="blocked_at_gate", pricing_eligible=False)

    region_a = SimpleNamespace(proposals=[proposal_a])
    region_b = SimpleNamespace(proposals=[proposal_b])
    cascade = ListingCascadeResult(
        regions=[region_a, region_b],
        region_evidence=[
            {"region_id": "region-0", "signals": {"bottom_parsed": {"set_code": "lea", "collector_number": "1"}}},
            {"region_id": "region-1", "signals": {"bottom_parsed": {"set_code": "mkm", "collector_number": "2"}}},
        ],
        all_proposals=[proposal_a, proposal_b],
        attach_rows=[],
        metrics={},
        fuse_output=None,
        skipped_region_count=0,
    )

    updated = apply_cascade_proposals_to_candidates(
        [candidate_a, candidate_b],
        cascade,
        listing_image_id="img-99",
        detection_id_by_region={"region-0": "det-a", "region-1": "det-b"},
        region_path_by_region={"region-0": "/crops/a.png", "region-1": "/crops/b.png"},
    )

    assert updated == 2
    assert candidate_a.evidence_json["gate_status"] == "verified"
    assert candidate_a.evidence_json["verification_detection_id"] == "det-a"
    assert candidate_a.evidence_json["cascade_region_id"] == "region-0"
    assert candidate_a.confidence_score == 0.91
    assert candidate_b.evidence_json["gate_status"] == "blocked_at_gate"
    assert candidate_b.evidence_json["cascade_region_id"] == "region-1"
