from __future__ import annotations

import re

# Substrings that usually indicate non-MTG inventory when matched loosely to card names.
NON_MTG_TITLE_PATTERNS = re.compile(
    r"\b(comic|poster|hoodie|t-?shirt|apparel|avatar\s+the\s+last\s+airbender|"
    r"avengers|marvel|dc\s+comics|funko|playmat|sleeves?\s+pack|deck\s+box)\b",
    re.IGNORECASE,
)

BULK_LOT_TITLE_PATTERNS = re.compile(
    r"\b(lot|bulk|job\s*lot|collection|bundle|repack|mystery|"
    r"\d{2,}\s*(cards?|card\s+lot)|cards?\s+lot|unsorted|assorted)\b",
    re.IGNORECASE,
)


def is_bulk_lot_title(title: str) -> bool:
    return bool(BULK_LOT_TITLE_PATTERNS.search(title or ""))


def is_non_mtg_listing(title: str) -> bool:
    return bool(NON_MTG_TITLE_PATTERNS.search(title or ""))
