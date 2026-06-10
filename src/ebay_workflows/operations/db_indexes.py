from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Browse API returns at most ~10,000 results per query (offset ceiling).
EBAY_BROWSE_MAX_OFFSET = 10_000

SCHEMA_PATCH_DDL: tuple[str, ...] = (
    "ALTER TABLE listings ADD COLUMN IF NOT EXISTS description_text TEXT",
)

PERFORMANCE_INDEX_DDL: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_listings_last_seen_at ON listings (last_seen_at)",
    "CREATE INDEX IF NOT EXISTS ix_listing_images_download_status ON listing_images (download_status)",
    "CREATE INDEX IF NOT EXISTS ix_listing_card_candidates_listing_rank "
    "ON listing_card_candidates (listing_id, rank_position)",
    "CREATE INDEX IF NOT EXISTS ix_listing_scores_rank_value ON listing_scores (rank_value DESC)",
    "CREATE INDEX IF NOT EXISTS ix_card_prices_scryfall_timestamp "
    "ON card_prices (scryfall_id, price_timestamp)",
    "CREATE INDEX IF NOT EXISTS ix_scryfall_cards_name ON scryfall_cards (name)",
)


def ensure_schema_patches(engine: Engine) -> list[str]:
    """Apply idempotent schema patches for databases created before Alembic migrations."""
    applied: list[str] = []
    with engine.begin() as conn:
        for ddl in SCHEMA_PATCH_DDL:
            conn.execute(text(ddl))
            applied.append(ddl.split("ADD COLUMN IF NOT EXISTS ")[1].split(" ")[0])
    return applied


def ensure_performance_indexes(engine: Engine) -> list[str]:
    """Apply idempotent btree indexes used by ingest and ranking queries."""
    applied: list[str] = []
    with engine.begin() as conn:
        for ddl in SCHEMA_PATCH_DDL:
            conn.execute(text(ddl))
        for ddl in PERFORMANCE_INDEX_DDL:
            conn.execute(text(ddl))
            applied.append(ddl.split("IF NOT EXISTS ")[1].split(" ON ")[0])
    return applied
