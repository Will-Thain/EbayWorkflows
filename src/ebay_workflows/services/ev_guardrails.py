from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..config import Settings
from .image_evidence import match_evidence_has_image_evidence
from .listing_condition import adjust_price_for_listing_condition
from .listing_filters import is_bulk_lot_title, is_non_mtg_listing


def title_match_allowed_for_pricing(
    listing_title: str,
    matched_card_name: str,
    match_score: float,
    settings: Settings,
) -> tuple[bool, str | None]:
    """Decide whether a fuzzy title match may drive Cardmarket pricing."""
    min_score = settings.title_match_min_score_for_pricing
    if match_score < min_score:
        return False, "match_score_below_threshold"

    if is_non_mtg_listing(listing_title):
        strict = settings.title_match_min_score_non_mtg
        if match_score < strict:
            return False, "non_mtg_title_low_confidence"

    if is_bulk_lot_title(listing_title):
        return False, "bulk_lot_title_requires_image_evidence"

    return True, None


def pricing_allowed_for_candidate(
    listing_title: str,
    matched_card_name: str,
    match_score: float,
    evidence: dict[str, Any],
    settings: Settings,
) -> tuple[bool, str | None]:
    """
    Allow Cardmarket pricing when image evidence confirms the match, otherwise
    fall back to title-match guardrails (bulk lots require crop evidence).
    """
    if evidence.get("image_verified"):
        source = evidence.get("image_verification_source")
        if source in {"set_collector", "set_symbol"}:
            return True, None

    return title_match_allowed_for_pricing(
        listing_title,
        matched_card_name,
        match_score,
        settings,
    )


def crop_match_allowed_for_pricing(
    listing_title: str,
    matched_card_name: str,
    match_score: float,
    match_evidence: dict[str, Any],
    *,
    scryfall_id: str | None,
    scryfall_card: Any | None,
    settings: Settings,
) -> tuple[bool, str | None]:
    """Phase 6: price lot crops when crop-level image evidence supports the match."""
    if is_bulk_lot_title(listing_title):
        ok, _source = match_evidence_has_image_evidence(
            match_evidence,
            scryfall_id,
            settings,
            scryfall_card=scryfall_card,
        )
        if ok:
            return True, None
        return False, "bulk_lot_no_crop_image_evidence"

    return title_match_allowed_for_pricing(
        listing_title,
        matched_card_name,
        match_score,
        settings,
    )


def sanitize_unit_price(
    price_amount: float | Decimal,
    *,
    match_score: float,
    settings: Settings,
) -> tuple[float | None, str | None]:
    """Drop or cap unrealistic Cardmarket unit prices used in EV."""
    value = float(price_amount)
    max_price = settings.cardmarket_max_unit_price_eur
    if value <= 0:
        return None, "non_positive_price"
    if value > max_price and match_score < 0.98:
        return None, "price_outlier_rejected"
    if value > max_price:
        return max_price, "price_outlier_capped"
    return value, None


def cap_ev_adjusted(
    ev_adjusted: Decimal,
    listing_cost: Decimal,
    settings: Settings,
) -> tuple[Decimal, bool]:
    """Cap rank EV relative to listing cost to limit false-positive blowups."""
    cap = listing_cost * Decimal(str(settings.ev_max_listing_cost_multiple))
    if ev_adjusted > cap:
        return cap, True
    return ev_adjusted, False


def apply_price_to_evidence(
    evidence: dict[str, Any],
    price_row: Any,
    *,
    listing_title: str,
    matched_card_name: str,
    match_score: float,
    settings: Settings,
    condition_text: str | None = None,
) -> bool:
    allowed, reason = pricing_allowed_for_candidate(
        listing_title,
        matched_card_name,
        match_score,
        evidence,
        settings,
    )
    if not allowed:
        evidence["cardmarket_price_rejected"] = {"reason": reason, "match_score": match_score}
        return False

    adjusted_price, grade, multiplier = adjust_price_for_listing_condition(
        float(price_row.price_amount),
        title=listing_title,
        condition_text=condition_text,
        settings=settings,
    )

    sanitized, price_reason = sanitize_unit_price(
        adjusted_price,
        match_score=match_score,
        settings=settings,
    )
    if sanitized is None:
        evidence["cardmarket_price_rejected"] = {
            "reason": price_reason,
            "raw_price_amount": float(price_row.price_amount),
            "adjusted_price_amount": adjusted_price,
            "match_score": match_score,
        }
        return False

    payload: dict[str, Any] = {
        "currency": price_row.currency,
        "price_amount": sanitized,
        "raw_price_amount": float(price_row.price_amount),
        "price_type": price_row.price_type,
        "price_timestamp": price_row.price_timestamp,
        "condition": price_row.condition,
        "language": price_row.language,
        "listing_condition_grade": grade,
        "condition_multiplier": multiplier,
    }
    if price_reason:
        payload["price_guard"] = price_reason
    evidence["cardmarket_price"] = payload
    return True
