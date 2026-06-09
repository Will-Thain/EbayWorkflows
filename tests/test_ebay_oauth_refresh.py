from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from ebay_workflows.exceptions import AuthenticationError
from ebay_workflows.integrations.ebay import _browse_search_page, _ebay_limiter
from ebay_workflows.config import Settings


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


def test_browse_search_refreshes_token_after_401() -> None:
    settings = _minimal_settings()
    limiter = _ebay_limiter(settings)
    client = MagicMock()
    headers = {"Authorization": "Bearer stale-token"}

    second = httpx.Response(200, request=httpx.Request("GET", "https://api.ebay.com/search"))
    second._content = b'{"itemSummaries": []}'

    with patch(
        "ebay_workflows.integrations.ebay._request_with_retry",
        side_effect=[AuthenticationError("eBay HTTP 401"), second],
    ) as request_mock:
        with patch(
            "ebay_workflows.integrations.ebay._oauth_token",
            return_value="fresh-token",
        ) as oauth_mock:
            response, token = _browse_search_page(
                client,
                settings=settings,
                limiter=limiter,
                browse_search_url="https://api.ebay.com/search",
                headers=headers,
                params={"q": "mtg", "limit": 10, "offset": 0},
            )

    assert token == "fresh-token"
    assert response.status_code == 200
    assert oauth_mock.call_count == 1
    assert request_mock.call_count == 2
    assert headers["Authorization"] == "Bearer fresh-token"
