"""Listing candidate verification — workflow policy on persisted evidence rows."""

from __future__ import annotations

from typing import Any

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings
from .candidate_gate import (
    apply_image_evidence_gate as _apply_image_evidence_gate,
    candidate_has_image_evidence as _candidate_has_image_evidence,
    demote_image_verification,
    evaluate_image_verification,
    is_verified_candidate,
    match_evidence_has_image_evidence as _match_evidence_has_image_evidence,
    region_zone_evidence_matches_card as _region_zone_evidence_matches_card,
    verification_strength,
)
from .candidate_selection import (
    apply_per_listing_verification_gates as _apply_per_listing_verification_gates,
    select_pricing_candidate,
)

__all__ = [
    "apply_image_evidence_gate",
    "apply_per_listing_verification_gates",
    "candidate_has_image_evidence",
    "demote_image_verification",
    "evaluate_image_verification",
    "is_verified_candidate",
    "match_evidence_has_image_evidence",
    "region_zone_evidence_matches_card",
    "select_pricing_candidate",
    "verification_strength",
]


def candidate_has_image_evidence(
    evidence: dict[str, Any],
    scryfall_id: str | None,
    settings: Settings,
    *,
    scryfall_card: Any | None = None,
) -> tuple[bool, str | None]:
    return _candidate_has_image_evidence(
        evidence,
        scryfall_id,
        coerce_recognition_settings(settings),
        scryfall_card=scryfall_card,
    )


def match_evidence_has_image_evidence(
    match_evidence: dict[str, Any],
    scryfall_id: str | None,
    settings: Settings,
    *,
    scryfall_card: Any | None = None,
) -> tuple[bool, str | None]:
    return _match_evidence_has_image_evidence(
        match_evidence,
        scryfall_id,
        coerce_recognition_settings(settings),
        scryfall_card=scryfall_card,
    )


def region_zone_evidence_matches_card(
    zone_evidence: dict[str, Any],
    fields: dict[str, tuple[str, float]],
    scryfall_card: Any,
    settings: Settings,
) -> bool:
    return _region_zone_evidence_matches_card(
        zone_evidence,
        fields,
        scryfall_card,
        coerce_recognition_settings(settings),
    )


def apply_image_evidence_gate(candidate: Any, settings: Settings) -> bool:
    return _apply_image_evidence_gate(candidate, coerce_recognition_settings(settings))


def apply_per_listing_verification_gates(
    candidates: list[Any],
    settings: Settings,
) -> tuple[int, int]:
    return _apply_per_listing_verification_gates(
        candidates,
        coerce_recognition_settings(settings),
    )
