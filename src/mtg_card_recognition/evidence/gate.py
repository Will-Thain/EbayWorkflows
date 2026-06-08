from __future__ import annotations

from typing import Any

from ..catalog.mana import scryfall_card_mana_colors
from ..config import RecognitionSettings
from ..identifiers import normalize_collector_number, normalize_set_code

_VERIFICATION_STRENGTH: dict[str, int] = {
    "set_collector": 30,
    "set_symbol": 20,
    "ocr": 5,
    "embedding": 3,
    "mana_colors": 1,
}


def verification_strength(source: str | None) -> int:
    if not source:
        return 0
    return _VERIFICATION_STRENGTH.get(source, 0)


def _identifiers_from_evidence(evidence: dict[str, Any]) -> tuple[str | None, str | None]:
    zone = evidence.get("zone_evidence") or {}
    bottom = zone.get("bottom_parsed") or {}
    set_code = normalize_set_code(bottom.get("set_code"))
    collector_number = normalize_collector_number(bottom.get("collector_number"))

    parsed = evidence.get("parsed_identifiers") or {}
    if parsed.get("set_code"):
        set_code = normalize_set_code(parsed.get("set_code"))
    if parsed.get("collector_number"):
        collector_number = normalize_collector_number(parsed.get("collector_number"))

    symbol = zone.get("set_symbol_match") or {}
    sym_code = normalize_set_code(symbol.get("set_code"))
    if sym_code and not set_code:
        set_code = sym_code
    return set_code, collector_number


def _card_identifiers_match_strict(
    scryfall_card: Any,
    set_code: str | None,
    collector_number: str | None,
) -> bool:
    """Set and collector must both match when claiming set_collector verification."""
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
    symbol = zone.get("set_symbol_match") or {}
    sym_code = normalize_set_code(symbol.get("set_code"))
    sym_score = float(symbol.get("score", 0.0))
    threshold = settings.card_set_symbol_min_score if min_score is None else min_score
    card_set = normalize_set_code(getattr(scryfall_card, "set_code", None))
    return bool(sym_code and card_set and sym_score >= threshold and sym_code == card_set)


def _hard_verify(evidence: dict[str, Any], scryfall_card: Any, settings: RecognitionSettings) -> bool:
    bottom = (evidence.get("zone_evidence") or {}).get("bottom_parsed") or {}
    set_code = normalize_set_code(bottom.get("set_code"))
    collector = normalize_collector_number(bottom.get("collector_number"))
    if not _card_identifiers_match_strict(scryfall_card, set_code, collector):
        return False
    name_ok = _name_similarity(evidence, scryfall_card) >= settings.verify_name_hard_min
    symbol_ok = _set_symbol_matches_card(
        evidence,
        scryfall_card,
        settings,
        min_score=settings.verify_symbol_strong_min,
    )
    return name_ok or symbol_ok


def _strong_verify_symbol(evidence: dict[str, Any], scryfall_card: Any, settings: RecognitionSettings) -> bool:
    if not _set_symbol_matches_card(
        evidence,
        scryfall_card,
        settings,
        min_score=settings.verify_symbol_strong_min,
    ):
        return False
    if _name_similarity(evidence, scryfall_card) < settings.verify_name_strong_min:
        return False
    bottom = (evidence.get("zone_evidence") or {}).get("bottom_parsed") or {}
    bottom_set = normalize_set_code(bottom.get("set_code"))
    if bottom_set:
        card_set = normalize_set_code(getattr(scryfall_card, "set_code", None))
        if not card_set or card_set != bottom_set:
            return False
    return True


def _lot_set_collector_verify(evidence: dict[str, Any], scryfall_card: Any) -> bool:
    if evidence.get("match_method") != "set_collector":
        return False
    parsed = evidence.get("parsed_identifiers") or {}
    return _card_identifiers_match_strict(
        scryfall_card,
        normalize_set_code(parsed.get("set_code")),
        normalize_collector_number(parsed.get("collector_number")),
    )


def evaluate_image_verification(
    evidence: dict[str, Any],
    scryfall_id: str | None,
    settings: RecognitionSettings,
    *,
    scryfall_card: Any | None = None,
) -> tuple[bool, str | None, int]:
    """Return (verified, source, strength) for one candidate."""
    if not scryfall_id or scryfall_card is None:
        return False, None, 0

    zone = evidence.get("zone_evidence") or {}
    if zone.get("zones_available"):
        if _hard_verify(evidence, scryfall_card, settings):
            return True, "set_collector", verification_strength("set_collector")
        if _strong_verify_symbol(evidence, scryfall_card, settings):
            return True, "set_symbol", verification_strength("set_symbol")
        return False, None, 0

    if _lot_set_collector_verify(evidence, scryfall_card):
        return True, "set_collector", verification_strength("set_collector")

    return False, None, 0


def region_zone_evidence_matches_card(
    zone_evidence: dict[str, Any],
    fields: dict[str, tuple[str, float]],
    scryfall_card: Any,
    settings: RecognitionSettings,
) -> bool:
    """Attach zone evidence only when the region plausibly references this printing."""
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
    if not zone_evidence.get("zones_available"):
        return False
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
    """Set image_verified / pricing_eligible on a single candidate (call after per-listing winner pick)."""
    evidence: dict[str, Any] = dict(candidate.evidence_json or {})
    scryfall_id = str(candidate.scryfall_id) if candidate.scryfall_id else None
    scryfall_card = getattr(candidate, "scryfall_card", None)
    verified, source = candidate_has_image_evidence(
        evidence,
        scryfall_id,
        settings,
        scryfall_card=scryfall_card,
    )

    evidence["image_verified"] = verified
    evidence["image_verification_source"] = source if verified else None
    if verified:
        evidence["pricing_eligible"] = True
        evidence.pop("pricing_reject_reason", None)
    else:
        evidence["pricing_eligible"] = False
        evidence["pricing_reject_reason"] = "no_image_reference"
        if "cardmarket_price" in evidence:
            evidence["cardmarket_price_rejected"] = {
                "reason": "no_image_reference",
                "previous_price": evidence.pop("cardmarket_price"),
            }
        candidate.confidence_score = min(float(candidate.confidence_score), 0.2)

    candidate.evidence_json = evidence
    return verified


def demote_image_verification(candidate: Any) -> None:
    """Clear verification and pricing on a candidate."""
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


# Legacy helpers kept for tests that inspect mana/symbol in isolation (not used for verify).
def _mana_colors_match_card(evidence: dict[str, Any], scryfall_card: Any, settings: RecognitionSettings) -> bool:
    zone = evidence.get("zone_evidence") or {}
    mana = zone.get("mana_cost") or {}
    detected = {str(c).upper() for c in (mana.get("colors") or []) if str(c).upper() in {"W", "U", "B", "R", "G"}}
    if not detected:
        return False
    confidence = float(mana.get("confidence", 0.0))
    if confidence < settings.image_evidence_min_mana_confidence:
        return False
    expected = scryfall_card_mana_colors(scryfall_card)
    if not expected:
        return False
    return bool(detected & expected)
