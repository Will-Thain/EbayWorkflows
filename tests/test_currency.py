from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from ebay_workflows.scoring.currency import convert_to_base_currency, listing_total_cost_base


def _settings(**overrides: object) -> SimpleNamespace:
    base = {"base_currency": "EUR", "fx_gbp_to_eur": 1.17, "fx_rates_to_base": {"GBP": 1.17}}
    base.update(overrides)
    return SimpleNamespace(**base)


def test_convert_gbp_to_eur() -> None:
    settings = _settings()
    assert convert_to_base_currency(Decimal("10"), "GBP", settings) == Decimal("11.70")


def test_listing_total_cost_base() -> None:
    listing = SimpleNamespace(price_amount=10, shipping_amount=2, currency="GBP")
    cost = listing_total_cost_base(listing, _settings())
    assert cost == Decimal("14.04")


def test_missing_fx_rate_raises() -> None:
    settings = _settings(fx_rates_to_base={})
    with pytest.raises(ValueError, match="No FX rate"):
        convert_to_base_currency(10, "GBP", settings)
