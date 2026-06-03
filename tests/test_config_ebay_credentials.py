from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from ebay_workflows.config import Settings

_REQUIRED = {
    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/ebay_workflows",
    "SCRYFALL_BULK_URI": "https://api.scryfall.com/bulk-data/default-cards",
    "CARDMARKET_BULK_FILE_PATH": "./samples/cardmarket_prices.csv",
    "IMAGE_CACHE_DIR": "./.cache/images",
    "FAISS_INDEX_PATH": "./.cache/faiss/index.bin",
    "GLOBAL_REQUESTS_PER_MINUTE_CAP": "90",
    "EBAY_REQUESTS_PER_MINUTE": "60",
}


def _settings(**overrides: str) -> Settings:
    env = {**_REQUIRED, **overrides}
    with patch.dict(os.environ, env, clear=True):
        return Settings()


def test_resolved_credentials_use_production_by_default() -> None:
    settings = _settings(
        EBAY_CLIENT_ID="prod-id",
        EBAY_CLIENT_SECRET="prod-secret",
        EBAY_SANDBOX_CLIENT_ID="sand-id",
        EBAY_SANDBOX_CLIENT_SECRET="sand-secret",
        EBAY_USE_SANDBOX="false",
        ENABLE_EBAY_API="true",
    )
    assert settings.resolved_ebay_client_id == "prod-id"
    assert settings.resolved_ebay_client_secret == "prod-secret"


def test_resolved_credentials_use_sandbox_when_enabled() -> None:
    settings = _settings(
        EBAY_CLIENT_ID="prod-id",
        EBAY_CLIENT_SECRET="prod-secret",
        EBAY_SANDBOX_CLIENT_ID="sand-id",
        EBAY_SANDBOX_CLIENT_SECRET="sand-secret",
        EBAY_USE_SANDBOX="true",
        ENABLE_EBAY_API="true",
    )
    assert settings.resolved_ebay_client_id == "sand-id"
    assert settings.resolved_ebay_client_secret == "sand-secret"


def test_sandbox_credentials_required_when_sandbox_enabled() -> None:
    with pytest.raises(ValueError, match="EBAY_SANDBOX_CLIENT_ID"):
        _settings(
            EBAY_CLIENT_ID="prod-id",
            EBAY_CLIENT_SECRET="prod-secret",
            EBAY_SANDBOX_CLIENT_ID="",
            EBAY_SANDBOX_CLIENT_SECRET="",
            EBAY_USE_SANDBOX="true",
            ENABLE_EBAY_API="true",
        )
