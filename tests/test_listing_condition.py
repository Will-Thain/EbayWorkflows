from __future__ import annotations

from ebay_workflows.config import Settings
from ebay_workflows.services.listing_condition import (
    adjust_price_for_listing_condition,
    parse_listing_condition,
)


def _settings(**overrides: object) -> Settings:
    base = {
        "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
        "SCRYFALL_BULK_URI": "https://example.com/bulk",
        "CARDMARKET_BULK_FILE_PATH": "./data/cardmarket/prices.csv",
        "IMAGE_CACHE_DIR": "./.cache/images",
        "FAISS_INDEX_PATH": "./.cache/faiss/index.bin",
        "GLOBAL_REQUESTS_PER_MINUTE_CAP": 90,
    }
    base.update(overrides)
    return Settings(**base)


def test_parse_listing_condition_from_title() -> None:
    assert parse_listing_condition("MTG Lightning Bolt LP") == "LP"
    assert parse_listing_condition("Sol Ring Near Mint") == "NM"


def test_condition_adjusts_cardmarket_price() -> None:
    settings = _settings()
    adjusted, grade, multiplier = adjust_price_for_listing_condition(
        10.0,
        title="Lightning Bolt LP",
        condition_text=None,
        settings=settings,
    )
    assert grade == "LP"
    assert multiplier == 0.85
    assert adjusted == 8.5
