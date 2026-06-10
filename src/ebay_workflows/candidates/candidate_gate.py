"""Image verification gate for EbayWorkflows candidate rows."""

from __future__ import annotations

from typing import Any

from ..adapters.recognition_settings import RecognitionSettings
from ..recognition.listing_identifiers import normalize_collector_number, normalize_set_code

_VERIFICATION_STRENGTH: dict[str, int] = {
    "set_collector": 30,
    "set_symbol": 20,
    "ocr": 5,
    "embedding": 3,
}


def verification_strength(source: str | None) -> int:
    if not source:
        return 0
    return _VERIFICATION_STRENGTH.get(source, 0)


def _card_identifiers_match_strict(
    scryfall_card: Any,
    set_code: str | None,
    collector_number: str | None,
) -> bool:
    if scryfall_card is None or not set_code or not collector_number:
        return False
    card_set = normalize_set_code(getattr(scryfall_card, "set_code", None))
    if not card_set or card_set != set_code:
        return False
    card_num = normalize_collector_number(getattr(scryfall_card, "collector_number", None))
    return card_num is not None and card_num == collector_number


def _name_similarity(evidence: dict[str, Any], scryfall_card: Any) -> float:
    from rapidfuzz import fuzz

    zone = evidence.get("zone_evidence") or {}
    ocr_title = zone.get("name_ocr") or ""
    if not ocr_title:
        ocr_block = evidence.get("ocr_verification") or {}
        ocr_title = str(ocr_block.get("ocr_title") or "")
    if not ocr_title or not getattr(scryfall_card, "name", None):
        return 0.0
    return fuzz.WRatio(ocr_title.lower(), scryfall_card.name.lower()) / 100.0


def _set_symbol_matches_card(
    evidence: dict[str, Any],
    scryfall_card: Any,
    settings: RecognitionSettings,
    *,
    min_score: float | None = None,
) -> bool:
    zone = evidence.get("zone_evidence") or {}
    symbol = zone.get("symbol_match") or zone.get("set_symbol_match") or {}
    sym_code = normalize_set_code(symbol.get("set_code"))
    sym_score = float(symbol.get("score", 0.0))
    threshold = settings.card_set_symbol_min_score if min_score is None else min_score
    card_set = normalize_set_code(getattr(scryfall_card, "set_code", None))
    return bool(sym_code and card_set and sym_score >= threshold and sym_code == card_set)


def evaluate_image_verification(
    evidence: dict[str, Any],
    scryfall_id: str | None,
    settings: RecognitionSettings,
    *,
    scryfall_card: Any | None = None,
) -> tuple[bool, str | None, int]:
    """Return (verified, source, strength) for one candidate.

    Only ``set_collector`` may verify for pricing. Cascade ``gate_status`` is
    authoritative when present — legacy heuristics must not upgrade blocked rows.
    """
    gate_status = evidence.get("gate_status")
    if gate_status is not None:
        if (
            gate_status == "verified"
            and evidence.get("pricing_eligible")
            and (evidence.get("verification_source") or "set_collector") == "set_collector"
        ):
            return True, "set_collector", verification_strength("set_collector")
        return False, None, 0

    if not scryfall_id or scryfall_card is None:
        return False, None, 0

    zone = evidence.get("zone_evidence") or {}
    bottom = zone.get("bottom_parsed") or {}
    set_code = normalize_set_code(bottom.get("set_code"))
    collector = normalize_collector_number(bottom.get("collector_number"))
    if _card_identifiers_match_strict(scryfall_card, set_code, collector):
        name_ok = _name_similarity(evidence, scryfall_card) >= settings.verify_name_hard_min
        symbol_ok = _set_symbol_matches_card(
            evidence,
            scryfall_card,
            settings,
            min_score=settings.verify_symbol_strong_min,
        )
        if name_ok or symbol_ok:
            return True, "set_collector", verification_strength("set_collector")

    return False, None, 0


def region_zone_evidence_matches_card(
    zone_evidence: dict[str, Any],
    fields: dict[str, tuple[str, float]],
    scryfall_card: Any,
    settings: RecognitionSettings,
) -> bool:
    evidence = {"zone_evidence": zone_evidence}
    if fields.get("title"):
        evidence["ocr_verification"] = {"ocr_title": fields["title"][0]}
    card_id = getattr(scryfall_card, "id", None)
    ok, _, _ = evaluate_image_verification(
        evidence,
        str(card_id) if card_id is not None else None,
        settings,
        scryfall_card=scryfall_card,
    )
    if ok:
        return True
    bottom = zone_evidence.get("bottom_parsed") or {}
    set_code = normalize_set_code(bottom.get("set_code"))
    collector = normalize_collector_number(bottom.get("collector_number"))
    return _card_identifiers_match_strict(scryfall_card, set_code, collector)


def candidate_has_image_evidence(
    evidence: dict[str, Any],
    scryfall_id: str | None,
    settings: RecognitionSettings,
    *,
    scryfall_card: Any | None = None,
) -> tuple[bool, str | None]:
    verified, source, _strength = evaluate_image_verification(
        evidence,
        scryfall_id,
        settings,
        scryfall_card=scryfall_card,
    )
    return verified, source


def match_evidence_has_image_evidence(
    match_evidence: dict[str, Any],
    scryfall_id: str | None,
    settings: RecognitionSettings,
    *,
    scryfall_card: Any | None = None,
) -> tuple[bool, str | None]:
    return candidate_has_image_evidence(
        match_evidence,
        scryfall_id,
        settings,
        scryfall_card=scryfall_card,
    )


def apply_image_evidence_gate(candidate: Any, settings: RecognitionSettings) -> bool:
    evidence: dict[str, Any] = dict(candidate.evidence_json or {})
    scryfall_id = str(candidate.scryfall_id) if candidate.scryfall_id else None
    scryfall_card = getattr(candidate, "scryfall_card", None)
    verified, source = candidate_has_image_evidence(
        evidence,
        scryfall_id,
        settings,
        scryfall_card=scryfall_card,
    )

    pricing_eligible = bool(verified and source == "set_collector")
    evidence["image_verified"] = verified
    evidence["image_verification_source"] = source if verified else None
    if pricing_eligible:
        evidence["pricing_eligible"] = True
        evidence.pop("pricing_reject_reason", None)
    else:
        evidence["pricing_eligible"] = False
        evidence["pricing_reject_reason"] = (
            "no_image_reference" if not verified else "symbol_only_not_pricing"
        )
        if "cardmarket_price" in evidence:
            evidence["cardmarket_price_rejected"] = {
                "reason": "no_image_reference",
                "previous_price": evidence.pop("cardmarket_price"),
            }
        candidate.confidence_score = min(float(candidate.confidence_score), 0.2)

    candidate.evidence_json = evidence
    return verified


def demote_image_verification(candidate: Any) -> None:
    evidence: dict[str, Any] = dict(candidate.evidence_json or {})
    evidence["image_verified"] = False
    evidence["image_verification_source"] = None
    evidence["pricing_eligible"] = False
    evidence["pricing_reject_reason"] = "superseded_by_listing_winner"
    if "cardmarket_price" in evidence:
        evidence["cardmarket_price_rejected"] = {
            "reason": "superseded_by_listing_winner",
            "previous_price": evidence.pop("cardmarket_price"),
        }
    candidate.evidence_json = evidence


def is_verified_candidate(candidate: Any) -> bool:
    evidence = candidate.evidence_json or {}
    return bool(evidence.get("image_verified"))
