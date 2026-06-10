from __future__ import annotations

import uuid
from types import SimpleNamespace

from mtg_card_recognition.cascade.models import Proposal
from mtg_card_recognition.pipeline.listing import ListingCascadeResult

from ebay_workflows.candidates.candidate_sync import (
    apply_cascade_proposals_to_candidates,
    pricing_winner_from_cascade,
)


def _proposal(
    printing_id: str,
    *,
    gate_status: str = "verified",
    pricing_eligible: bool = True,
) -> Proposal:
    return Proposal(
        printing_id=printing_id,
        gate_status=gate_status,
        pricing_eligible=pricing_eligible,
        verification_source="set_collector",
        image_verified=gate_status == "verified",
        corroboration_score=0.85,
    )


def _cascade_with_one_region(proposal: Proposal) -> ListingCascadeResult:
    region = SimpleNamespace(proposals=[proposal])
    return ListingCascadeResult(
        regions=[region],
        region_evidence=[
            {
                "region_id": "region-0",
                "signals": {"bottom_parsed": {"set_code": "lea", "collector_number": "1"}},
            }
        ],
        all_proposals=[proposal],
        attach_rows=[],
        metrics={},
        fuse_output=None,
        skipped_region_count=0,
    )


def test_apply_cascade_proposals_merges_gate_and_provenance() -> None:
    card_id = uuid.uuid4()
    candidate = SimpleNamespace(
        scryfall_id=card_id,
        confidence_score=0.5,
        evidence_json={},
    )
    proposal = _proposal(str(card_id))
    cascade = _cascade_with_one_region(proposal)

    updated = apply_cascade_proposals_to_candidates(
        [candidate],
        cascade,
        listing_image_id="img-1",
        detection_id_by_region={"region-0": "det-1"},
        region_path_by_region={"region-0": "/tmp/crop.png"},
    )

    assert updated == 1
    assert candidate.evidence_json["gate_status"] == "verified"
    assert candidate.evidence_json["pricing_eligible"] is True
    assert candidate.evidence_json["verification_listing_image_id"] == "img-1"
    assert candidate.evidence_json["verification_detection_id"] == "det-1"
    assert candidate.evidence_json["cascade_region_id"] == "region-0"
    assert candidate.confidence_score == 0.85


def test_apply_cascade_skips_unknown_printing() -> None:
    candidate = SimpleNamespace(
        scryfall_id=uuid.uuid4(),
        confidence_score=0.5,
        evidence_json={},
    )
    other_id = str(uuid.uuid4())
    cascade = _cascade_with_one_region(_proposal(other_id))

    updated = apply_cascade_proposals_to_candidates(
        [candidate],
        cascade,
        listing_image_id="img-1",
        detection_id_by_region={"region-0": "det-1"},
        region_path_by_region={"region-0": "/tmp/crop.png"},
    )

    assert updated == 0
    assert candidate.evidence_json == {}


def test_pricing_winner_from_cascade_returns_verified_proposal() -> None:
    winner = _proposal("win-id", gate_status="verified", pricing_eligible=True)
    blocked = _proposal("lose-id", gate_status="blocked_at_gate", pricing_eligible=False)
    cascade = ListingCascadeResult(
        regions=[],
        region_evidence=[],
        all_proposals=[blocked, winner],
        attach_rows=[],
        metrics={},
        fuse_output=None,
        skipped_region_count=0,
    )
    assert pricing_winner_from_cascade(cascade) is winner
