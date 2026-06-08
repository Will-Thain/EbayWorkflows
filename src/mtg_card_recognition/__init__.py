"""
MTG card recognition library — zone OCR, evidence gating, embeddings.

Designed for extraction into a standalone repository; eBay Workflows integrates
via ebay_workflows.adapters.recognition_settings.
"""

from .config import RecognitionSettings
from .evidence import (
    apply_image_evidence_gate,
    apply_per_listing_verification_gates,
    candidate_has_image_evidence,
    candidates_for_region_evidence,
    is_verified_candidate,
    match_evidence_has_image_evidence,
    merge_verification_provenance,
    region_zone_evidence_matches_card,
    select_pricing_candidate,
    zone_evidence_with_provenance,
)

__all__ = [
    "RecognitionSettings",
    "candidates_for_region_evidence",
    "merge_verification_provenance",
    "zone_evidence_with_provenance",
    "apply_image_evidence_gate",
    "apply_per_listing_verification_gates",
    "candidate_has_image_evidence",
    "is_verified_candidate",
    "match_evidence_has_image_evidence",
    "region_zone_evidence_matches_card",
    "select_pricing_candidate",
]

__version__ = "0.1.0"
