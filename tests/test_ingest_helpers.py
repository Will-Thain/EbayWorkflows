from __future__ import annotations

from types import SimpleNamespace

from ebay_workflows.operations.ingest_helpers import (
    EBAY_BROWSE_MAX_OFFSET,
    max_listings_per_query,
    resolve_max_pages,
)


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "ebay_max_pages_per_run": 20,
        "ebay_page_size": 50,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_resolve_max_pages_uses_cli_override() -> None:
    settings = _settings(ebay_max_pages_per_run=20)
    assert resolve_max_pages(5, settings) == 5


def test_resolve_max_pages_uses_env_default() -> None:
    settings = _settings(ebay_max_pages_per_run=20)
    assert resolve_max_pages(None, settings) == 20


def test_max_listings_per_query_caps_at_ebay_offset() -> None:
    settings = _settings(ebay_page_size=50)
    # 500 pages would exceed 10k offset — capped at 200 pages × 50 = 10_000
    assert max_listings_per_query(settings, 500) == EBAY_BROWSE_MAX_OFFSET
