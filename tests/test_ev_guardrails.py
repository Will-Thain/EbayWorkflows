from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from ebay_workflows.services.ev_guardrails import (
    cap_ev_adjusted,
    crop_match_allowed_for_pricing,
    pricing_allowed_for_candidate,
    sanitize_unit_price,
    title_match_allowed_for_pricing,
)
from ebay_workflows.services.listing_filters import is_bulk_lot_title, is_non_mtg_listing, is_probable_single_card_listing


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        title_match_min_score_for_pricing=0.88,
        title_match_min_score_non_mtg=0.98,
        cardmarket_max_unit_price_eur=250.0,
        ev_max_listing_cost_multiple=10.0,
        image_evidence_min_ocr_similarity=0.65,
        image_evidence_min_faiss_score=0.65,
        card_set_symbol_min_score=0.45,
    )


def test_bulk_lot_title_rejected_for_pricing() -> None:
    allowed, reason = title_match_allowed_for_pricing(
        "500 Time Spiral Basic Land Bulk Lot MTG Magic Cards",
        "Time Spiral",
        0.95,
        _settings(),
    )
    assert allowed is False
    assert reason == "bulk_lot_title_requires_image_evidence"


def test_crop_match_evidence_allows_bulk_lot_pricing() -> None:
    card = SimpleNamespace(id="abc-123", name="Lightning Bolt", set_code="LEA", collector_number="1")
    match_evidence = {
        "image_verified": True,
        "image_verification_source": "set_collector",
        "zone_evidence": {
            "bottom_parsed": {"set_code": "lea", "collector_number": "1"},
            "name_ocr": "Lightning Bolt",
        },
    }
    allowed, reason = crop_match_allowed_for_pricing(
        "500 card bulk lot MTG magic",
        card.name,
        0.72,
        match_evidence,
        scryfall_id=str(card.id),
        scryfall_card=card,
        settings=_settings(),
    )
    assert allowed is True
    assert reason is None


def test_image_verified_candidate_bypasses_title_pricing_gate() -> None:
    evidence = {
        "image_verified": True,
        "image_verification_source": "set_collector",
        "pricing_eligible": True,
        "match_score": 0.5,
    }
    allowed, reason = pricing_allowed_for_candidate(
        "Some listing",
        "Lightning Bolt",
        0.5,
        evidence,
        _settings(),
    )
    assert allowed is True
    assert reason is None


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
    assert is_bulk_lot_title("MTG Lots - Rare and Mythic")
    assert not is_bulk_lot_title("Lightning Bolt M11 LP")
    assert is_non_mtg_listing("Official Magic hoodie black")


def test_probable_single_card_listing() -> None:
    assert is_probable_single_card_listing("Spider-Man 2099 150 MTG R NM")
    assert is_probable_single_card_listing("NM Bloodbraid Elf Secret Lair 30th Anniversary")
    assert not is_probable_single_card_listing("30 Rare Magic: The Gathering Cards - Booster Pack")
    assert not is_probable_single_card_listing("Monster Protectors Prism Gold Playmat Tube")
    assert not is_probable_single_card_listing("MTG Rares - 6 play sets - 24 Total")
    assert not is_probable_single_card_listing("Magic the Gathering Card Bundles 50+ Cards")
    assert not is_probable_single_card_listing("(5) Promo Foils Gargos Invoke Despair")
