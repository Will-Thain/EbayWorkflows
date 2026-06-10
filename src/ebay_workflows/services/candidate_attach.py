"""Attach region OCR/zone evidence to listing candidates (EbayWorkflows)."""

from __future__ import annotations

from typing import Any

from mtg_card_recognition.identifiers import normalize_collector_number, normalize_set_code


def _set_collector_from_region(
    fields: dict[str, tuple[str, float]],
    zone_evidence: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    bottom = (zone_evidence or {}).get("bottom_parsed") or {}
    field_set = fields.get("set_code", ("", 0))[0] if "set_code" in fields else None
    set_code = normalize_set_code(field_set)
    if not set_code:
        set_code = normalize_set_code(bottom.get("set_code"))
    collector = normalize_collector_number(
        fields.get("collector_number", ("", 0))[0] if "collector_number" in fields else None
    )
    if not collector:
        collector = normalize_collector_number(bottom.get("collector_number"))
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
    """Return candidates that may receive OCR/zone evidence from one crop."""
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

    try:
        from rapidfuzz import fuzz
    except ImportError:
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


def update_candidate_ocr_confidence(
    candidate: Any,
    ocr_title: str,
    *,
    listing_image_id: str | None = None,
    detection_id: str | None = None,
    region_path: str | None = None,
) -> bool:
    """Apply OCR from one crop to a single candidate."""
    from rapidfuzz import fuzz

    scryfall_card = getattr(candidate, "scryfall_card", None)
    if not scryfall_card or not getattr(scryfall_card, "name", None):
        return False
    similarity = fuzz.WRatio(ocr_title.lower(), scryfall_card.name.lower()) / 100.0
    if similarity < 0.55:
        return False

    evidence = dict(getattr(candidate, "evidence_json", None) or {})
    existing = evidence.get("ocr_verification") or {}
    existing_sim = float(existing.get("similarity", 0.0))
    if similarity <= existing_sim:
        return False

    confidence = float(getattr(candidate, "confidence_score", 0.0))
    if similarity >= 0.8:
        confidence = min(1.0, confidence + 0.1)

    ocr_block: dict[str, Any] = {
        "ocr_title": ocr_title,
        "similarity": similarity,
        "method": "rapidfuzz_wratio",
    }
    if listing_image_id and detection_id and region_path:
        ocr_block["listing_image_id"] = listing_image_id
        ocr_block["detection_id"] = detection_id
        ocr_block["region_image_path"] = region_path
        evidence = merge_verification_provenance(
            evidence,
            listing_image_id=listing_image_id,
            detection_id=detection_id,
            region_path=region_path,
        )

    evidence["ocr_verification"] = ocr_block
    candidate.confidence_score = confidence
    candidate.evidence_json = evidence
    return True


def merge_verification_provenance(
    evidence: dict[str, Any],
    *,
    listing_image_id: str,
    detection_id: str,
    region_path: str,
) -> dict[str, Any]:
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
