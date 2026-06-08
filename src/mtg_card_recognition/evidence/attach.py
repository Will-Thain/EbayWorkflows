from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from ..identifiers import normalize_collector_number, normalize_set_code
from ..zones.signals import identifiers_from_fields


def _set_collector_from_region(
    fields: dict[str, tuple[str, float]],
    zone_evidence: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    bottom = (zone_evidence or {}).get("bottom_parsed") or {}
    ids = identifiers_from_fields(fields or {})
    set_code = normalize_set_code(ids.set_code or bottom.get("set_code"))
    collector = normalize_collector_number(ids.collector_number or bottom.get("collector_number"))
    return set_code, collector


def _printing_matches_region(
    scryfall_card: Any,
    set_code: str | None,
    collector_number: str | None,
) -> bool:
    if not set_code or not collector_number:
        return False
    card_set = normalize_set_code(getattr(scryfall_card, "set_code", None))
    card_num = normalize_collector_number(getattr(scryfall_card, "collector_number", None))
    return card_set == set_code and card_num is not None and card_num == collector_number


def candidates_for_region_evidence(
    candidates: list[Any],
    *,
    ocr_title: str | None,
    fields: dict[str, tuple[str, float]],
    zone_evidence: dict[str, Any] | None = None,
) -> list[Any]:
    """
    Return candidates that may receive OCR/zone evidence from one crop.

    Set+collector routes to matching printings. Name-only OCR attaches to at most
    one candidate; ambiguous reprints (same name, different printing) get none.
    """
    set_code, collector = _set_collector_from_region(fields, zone_evidence)
    if set_code and collector:
        return [
            candidate
            for candidate in candidates
            if getattr(candidate, "scryfall_card", None)
            and _printing_matches_region(candidate.scryfall_card, set_code, collector)
        ]

    if not ocr_title:
        return []

    name_matches: list[Any] = []
    for candidate in candidates:
        card = getattr(candidate, "scryfall_card", None)
        if not card or not getattr(card, "name", None):
            continue
        similarity = fuzz.WRatio(ocr_title.lower(), card.name.lower()) / 100.0
        if similarity >= 0.55:
            name_matches.append(candidate)

    if len(name_matches) == 1:
        return name_matches
    return []


def merge_verification_provenance(
    evidence: dict[str, Any],
    *,
    listing_image_id: str,
    detection_id: str,
    region_path: str,
) -> dict[str, Any]:
    """Attach image-region provenance to candidate evidence."""
    merged = dict(evidence)
    merged["verification_listing_image_id"] = listing_image_id
    merged["verification_detection_id"] = detection_id
    merged["verification_region_path"] = region_path
    return merged


def zone_evidence_with_provenance(
    zone_evidence: dict[str, Any],
    *,
    listing_image_id: str,
    detection_id: str,
    region_path: str,
) -> dict[str, Any]:
    payload = dict(zone_evidence)
    payload["listing_image_id"] = listing_image_id
    payload["detection_id"] = detection_id
    payload["region_image_path"] = region_path
    return payload
