from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from ebay_workflows.services.ev_guardrails import (
    cap_ev_adjusted,
    sanitize_unit_price,
    title_match_allowed_for_pricing,
)
from ebay_workflows.services.listing_filters import is_bulk_lot_title, is_non_mtg_listing


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        title_match_min_score_for_pricing=0.88,
        title_match_min_score_non_mtg=0.98,
        cardmarket_max_unit_price_eur=250.0,
        ev_max_listing_cost_multiple=10.0,
    )


def test_rejects_avengers_armageddon_loose_match() -> None:
    allowed, reason = title_match_allowed_for_pricing(
        "AVENGERS ARMAGEDDON #1 comic",
        "Armageddon",
        0.95,
        _settings(),
    )
    assert allowed is False
    assert reason == "non_mtg_title_low_confidence"


def test_rejects_outlier_price_without_high_match() -> None:
    price, reason = sanitize_unit_price(2500.0, match_score=0.9, settings=_settings())
    assert price is None
    assert reason == "price_outlier_rejected"


def test_caps_ev_to_listing_multiple() -> None:
    capped, was_capped = cap_ev_adjusted(Decimal("5000"), Decimal("10"), _settings())
    assert was_capped is True
    assert capped == Decimal("100")


def test_bulk_lot_title_detection() -> None:
    assert is_bulk_lot_title("MTG 500 card bulk job lot")
    assert not is_bulk_lot_title("Lightning Bolt M11 LP")
    assert is_non_mtg_listing("Official Magic hoodie black")
