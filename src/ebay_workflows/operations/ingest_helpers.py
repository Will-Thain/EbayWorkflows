from __future__ import annotations

from ..config import Settings

# eBay Browse search offset cannot exceed this value for a single query.
EBAY_BROWSE_MAX_OFFSET = 10_000


def resolve_max_pages(cli_override: int | None, settings: Settings) -> int:
    """Use CLI --max-pages when provided, otherwise EBAY_MAX_PAGES_PER_RUN."""
    if cli_override is not None:
        return cli_override
    return settings.ebay_max_pages_per_run


def max_listings_per_query(settings: Settings, max_pages: int) -> int:
    """Upper bound on listings fetched for one query/run."""
    capped_pages = min(max_pages, EBAY_BROWSE_MAX_OFFSET // max(settings.ebay_page_size, 1))
    return capped_pages * settings.ebay_page_size
