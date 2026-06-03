from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..config import Settings
from .listing_filters import is_non_mtg_listing


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
    return True, None


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
) -> bool:
    allowed, reason = title_match_allowed_for_pricing(
        listing_title, matched_card_name, match_score, settings
    )
    if not allowed:
        evidence["cardmarket_price_rejected"] = {"reason": reason, "match_score": match_score}
        return False

    sanitized, price_reason = sanitize_unit_price(
        float(price_row.price_amount),
        match_score=match_score,
        settings=settings,
    )
    if sanitized is None:
        evidence["cardmarket_price_rejected"] = {
            "reason": price_reason,
            "raw_price_amount": float(price_row.price_amount),
            "match_score": match_score,
        }
        return False

    payload: dict[str, Any] = {
        "currency": price_row.currency,
        "price_amount": sanitized,
        "price_type": price_row.price_type,
        "price_timestamp": price_row.price_timestamp,
        "condition": price_row.condition,
        "language": price_row.language,
    }
    if price_reason:
        payload["price_guard"] = price_reason
    evidence["cardmarket_price"] = payload
    return True
