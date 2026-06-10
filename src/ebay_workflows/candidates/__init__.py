"""Candidate row policy: gate, attach, sync, selection."""

from .candidate_attach import (
    candidates_for_region_evidence,
    merge_verification_provenance,
    update_candidate_ocr_confidence,
    zone_evidence_with_provenance,
)
from .candidate_gate import (
    apply_image_evidence_gate,
    candidate_has_image_evidence,
    demote_image_verification,
    evaluate_image_verification,
    is_verified_candidate,
    match_evidence_has_image_evidence,
    region_zone_evidence_matches_card,
    verification_strength,
)
from .candidate_selection import apply_per_listing_verification_gates, select_pricing_candidate
from .candidate_sync import apply_cascade_proposals_to_candidates, pricing_winner_from_cascade
from .image_evidence import (
    apply_per_listing_verification_gates as apply_per_listing_verification_gates_with_settings,
)

__all__ = [
    "apply_cascade_proposals_to_candidates",
    "apply_image_evidence_gate",
    "apply_per_listing_verification_gates",
    "apply_per_listing_verification_gates_with_settings",
    "candidate_has_image_evidence",
    "candidates_for_region_evidence",
    "demote_image_verification",
    "evaluate_image_verification",
    "is_verified_candidate",
    "match_evidence_has_image_evidence",
    "merge_verification_provenance",
    "pricing_winner_from_cascade",
    "region_zone_evidence_matches_card",
    "select_pricing_candidate",
    "update_candidate_ocr_confidence",
    "verification_strength",
    "zone_evidence_with_provenance",
]
