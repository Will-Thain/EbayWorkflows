"""Sync v0.3 cascade outputs onto EbayWorkflows listing candidates."""

from __future__ import annotations

from typing import Any

from ..recognition.cascade_bridge import ListingCascadeResult, Proposal, proposal_to_evidence
from .candidate_attach import merge_verification_provenance


def apply_cascade_proposals_to_candidates(
    candidates: list[Any],
    cascade: ListingCascadeResult,
    *,
    listing_image_id: str,
    detection_id_by_region: dict[str, str],
    region_path_by_region: dict[str, str],
) -> int:
    """Merge cascade gate fields onto matching ``ListingCardCandidate`` rows."""
    by_id = {
        str(candidate.scryfall_id): candidate
        for candidate in candidates
        if candidate.scryfall_id
    }
    updated = 0

    for index, (region_result, evidence_row) in enumerate(
        zip(cascade.regions, cascade.region_evidence, strict=False)
    ):
        region_id = str(evidence_row.get("region_id", f"region-{index}"))
        detection_id = detection_id_by_region.get(region_id, "")
        region_path = region_path_by_region.get(region_id, "")
        zone_payload = evidence_row.get("signals") or {}

        for proposal in region_result.proposals:
            candidate = by_id.get(proposal.printing_id)
            if candidate is None:
                continue
            evidence = dict(candidate.evidence_json or {})
            if detection_id and region_path:
                evidence = merge_verification_provenance(
                    evidence,
                    listing_image_id=listing_image_id,
                    detection_id=detection_id,
                    region_path=region_path,
                )
            evidence.update(proposal_to_evidence(proposal))
            evidence["zone_evidence"] = zone_payload
            evidence["cascade_region_id"] = region_id
            candidate.evidence_json = evidence
            candidate.confidence_score = max(
                float(candidate.confidence_score or 0.0),
                float(proposal.corroboration_score or 0.0),
            )
            updated += 1

    for attach in cascade.attach_rows:
        candidate = by_id.get(str(attach.get("printing_id")))
        if candidate is None:
            continue
        evidence = dict(candidate.evidence_json or {})
        evidence.update(attach)
        candidate.evidence_json = evidence

    return updated


def pricing_winner_from_cascade(cascade: ListingCascadeResult) -> Proposal | None:
    """Return the single pricing-eligible proposal after listing finalize."""
    for proposal in cascade.all_proposals:
        if proposal.pricing_eligible and proposal.gate_status == "verified":
            return proposal
    return None
