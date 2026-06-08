from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings


def convert_to_base_currency(
    amount: float | Decimal,
    from_currency: str,
    settings: Settings,
) -> Decimal:
    """Convert a monetary amount into BASE_CURRENCY using configured FX rates."""
    value = Decimal(str(amount))
    source = (from_currency or getattr(settings, "base_currency", "EUR")).upper()
    target = getattr(settings, "base_currency", "EUR").upper()
    if source == target:
        return value

    rates = getattr(settings, "fx_rates_to_base", None)
    if rates is None:
        target = getattr(settings, "base_currency", "EUR").upper()
        rates = {}
        fx_gbp = getattr(settings, "fx_gbp_to_eur", None)
        if target == "EUR" and fx_gbp is not None:
            rates["GBP"] = fx_gbp
    rate = rates.get(source)
    if rate is None:
        raise ValueError(
            f"No FX rate configured for {source} -> {target}. "
            f"Set FX_{source}_TO_{target} in .env (see docs/future-pain-points.md)."
        )
    return value * Decimal(str(rate))


def listing_total_cost_base(listing: object, settings: Settings) -> Decimal:
    """Listing price + shipping in BASE_CURRENCY."""
    price = getattr(listing, "price_amount", 0)
    shipping = getattr(listing, "shipping_amount", None) or 0
    currency = getattr(listing, "currency", getattr(settings, "base_currency", "EUR"))
    return convert_to_base_currency(Decimal(str(price)) + Decimal(str(shipping)), currency, settings)
