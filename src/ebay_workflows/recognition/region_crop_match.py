"""Phase 6 per-crop match via v0.3 cascade (no FAISS-only override)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from mtg_card_recognition.catalog.lookup import CatalogIndex
from mtg_card_recognition.cascade.models import Proposal
from mtg_card_recognition.config import RecognitionSettings
from mtg_card_recognition.embeddings.search import EmbeddingMatch
from mtg_card_recognition.identifiers import ParsedCardIdentifiers
from mtg_card_recognition.pipeline.region import run_region_from_image

from .listing_identifiers import merge_identifiers, parse_card_identifiers
from .title_match import ScryfallTitleIndex, TitleMatchResult, best_card_match_for_text


def _proposal_evidence(proposal: Proposal) -> dict[str, Any]:
    return {
        "match_method": proposal.verification_source or "cascade",
        "gate_status": proposal.gate_status,
        "pricing_eligible": proposal.pricing_eligible,
        "verification_source": proposal.verification_source,
        "image_verified": proposal.image_verified,
        "image_verification_source": proposal.verification_source if proposal.image_verified else None,
    }


def _pick_proposal(proposals: list[Proposal]) -> Proposal | None:
    verified = [
        proposal
        for proposal in proposals
        if proposal.gate_status == "verified" and proposal.pricing_eligible
    ]
    if verified:
        return verified[0]

    active = [proposal for proposal in proposals if proposal.review_status == "active"]
    if not active:
        return None
    return max(active, key=lambda proposal: proposal.corroboration_score)


def resolve_lot_crop_match(
    *,
    ocr_title: str,
    crop_path: str | None,
    catalog: CatalogIndex,
    title_index: ScryfallTitleIndex,
    set_collector_index: dict[tuple[str, str], str],
    card_by_id: dict[str, Any],
    recognition: RecognitionSettings,
    prefilter_size: int,
    score_cutoff: float,
    extra_identifiers: ParsedCardIdentifiers | None = None,
    search_fn: Callable[[str], list[EmbeddingMatch]] | None = None,
) -> tuple[Any | None, float, dict[str, Any]]:
    """Match a bulk-lot crop using the v0.3 image cascade; title match is fallback only."""
    evidence: dict[str, Any] = {}
    zone_dir = str(Path(recognition.image_cache_dir) / "lot_zones")

    if crop_path and Path(crop_path).is_file():
        result = run_region_from_image(
            crop_path,
            catalog=catalog,
            settings=recognition,
            search_fn=search_fn,
            listing_title=ocr_title,
            zone_dir=zone_dir,
        )
        if result.signals is not None:
            evidence["zone_evidence"] = result.signals.to_dict()
        if result.skipped:
            evidence["cascade_skipped"] = str(result.skip_reason)

        proposal = _pick_proposal(result.proposals)
        if proposal is not None:
            card = card_by_id.get(proposal.printing_id)
            if card is not None:
                evidence.update(_proposal_evidence(proposal))
                return card, float(proposal.corroboration_score or 0.0), evidence

    identifiers = merge_identifiers(
        extra_identifiers or ParsedCardIdentifiers(),
        parse_card_identifiers(ocr_title),
    )
    if identifiers.set_code or identifiers.collector_number:
        evidence["parsed_identifiers"] = {
            "set_code": identifiers.set_code,
            "collector_number": identifiers.collector_number,
        }

    title_result: TitleMatchResult | None = best_card_match_for_text(
        ocr_title,
        title_index,
        set_collector_index,
        card_by_id,
        prefilter_size=prefilter_size,
        score_cutoff=score_cutoff,
        extra_identifiers=identifiers,
    )
    if title_result is None:
        return None, 0.0, evidence

    card = card_by_id.get(title_result.card_id)
    if card is None:
        return None, 0.0, evidence

    evidence["match_method"] = title_result.match_method
    return card, title_result.score, evidence
