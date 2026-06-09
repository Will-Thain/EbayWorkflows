from __future__ import annotations

import os
from unittest.mock import patch

from ebay_workflows.adapters.recognition_settings import recognition_settings_from_app
from ebay_workflows.config import Settings

_REQUIRED = {
    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/ebay_workflows",
    "SCRYFALL_BULK_URI": "https://api.scryfall.com/bulk-data/default-cards",
    "CARDMARKET_BULK_FILE_PATH": "./samples/cardmarket_prices.csv",
    "IMAGE_CACHE_DIR": "./.cache/images",
    "FAISS_INDEX_PATH": "./.cache/faiss/index.bin",
    "GLOBAL_REQUESTS_PER_MINUTE_CAP": "90",
    "ENABLE_EBAY_API": "false",
    "DISABLE_LIVE_API_WRITES": "true",
}


def _settings(**overrides: str) -> Settings:
    env = {**_REQUIRED, **overrides}
    with patch.dict(os.environ, env, clear=True):
        return Settings()


def test_lot_crop_alias_on_settings() -> None:
    settings = _settings(LOT_CROP_MIN_COMBINED_CONFIDENCE="0.51")
    recognition = recognition_settings_from_app(settings)

    assert settings.phase6_min_crop_match_confidence == 0.51
    assert recognition.lot_crop_min_combined_confidence == 0.51


def test_faiss_build_fields_map_to_recognition() -> None:
    settings = _settings(
        FAISS_BUILD_MAX_CARDS="7500",
        FAISS_BUILD_ALL_CARDS="true",
    )
    recognition = recognition_settings_from_app(settings)

    assert recognition.faiss_build_max_cards == 7500
    assert recognition.faiss_build_all_cards is True
