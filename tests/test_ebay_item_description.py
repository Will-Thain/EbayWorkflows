from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from ebay_workflows.config import Settings
from ebay_workflows.integrations.ebay import (
    _extract_description_from_item_payload,
    _normalize_description_text,
    enrich_record_description,
    fetch_item_description,
)
from ebay_workflows.integrations.ebay import ListingRecord


def _minimal_settings(**overrides: object) -> Settings:
    base = {
        "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
        "SCRYFALL_BULK_URI": "https://example.com/bulk",
        "CARDMARKET_BULK_FILE_PATH": "./data/cardmarket/prices.csv",
        "IMAGE_CACHE_DIR": "./.cache/images",
        "FAISS_INDEX_PATH": "./.cache/faiss/index.bin",
        "GLOBAL_REQUESTS_PER_MINUTE_CAP": 90,
        "EBAY_CLIENT_ID": "id",
        "EBAY_CLIENT_SECRET": "secret",
        "EBAY_REQUESTS_PER_MINUTE": 60,
        "ENABLE_EBAY_API": True,
        "DISABLE_LIVE_API_WRITES": True,
    }
    base.update(overrides)
    return Settings(**base)


def test_normalize_description_text_strips_html() -> None:
    assert _normalize_description_text("<p>NM <b>Lightning Bolt</b></p>") == "NM Lightning Bolt"


def test_extract_description_prefers_full_description() -> None:
    payload = {
        "shortDescription": "Short",
        "description": "<p>Full item text</p>",
    }
    assert _extract_description_from_item_payload(payload) == "Full item text"


def test_fetch_item_description_returns_normalized_text() -> None:
    settings = _minimal_settings()
    response = httpx.Response(
        200,
        request=httpx.Request("GET", "https://api.ebay.com/item"),
        json={"description": "<p>Set: M10</p>"},
    )
    with patch("ebay_workflows.integrations.ebay.httpx.Client") as client_cls:
        client = MagicMock()
        client_cls.return_value.__enter__.return_value = client
        with patch("ebay_workflows.integrations.ebay._oauth_token", return_value="token"):
            with patch(
                "ebay_workflows.integrations.ebay._browse_item_page",
                return_value=(response, "token"),
            ):
                assert fetch_item_description(settings, "v1|123|0") == "Set: M10"


def test_enrich_record_description_skips_when_present() -> None:
    settings = _minimal_settings()
    record = ListingRecord(
        external_listing_id="v1|1|0",
        title="Bolt",
        listing_url="https://example.com",
        currency="GBP",
        price_amount=1.0,
        shipping_amount=None,
        condition_text=None,
        image_urls=[],
        raw_payload={},
        description_text="Already here",
    )
    with patch("ebay_workflows.integrations.ebay.fetch_item_description") as fetch_mock:
        enriched = enrich_record_description(settings, record)
    fetch_mock.assert_not_called()
    assert enriched.description_text == "Already here"
