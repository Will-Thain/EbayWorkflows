from __future__ import annotations

import re

# Substrings that usually indicate non-MTG inventory when matched loosely to card names.
NON_MTG_TITLE_PATTERNS = re.compile(
    r"\b(comic|poster|hoodie|t-?shirt|apparel|avatar\s+the\s+last\s+airbender|"
    r"avengers|marvel|dc\s+comics|funko|playmat|sleeves?\s+pack|deck\s+box)\b",
    re.IGNORECASE,
)

BULK_LOT_TITLE_PATTERNS = re.compile(
    r"\b(lots?|bulk|job\s*lot|collection|bundle|repacks?|mystery|"
    r"play\s*sets?|booster\s*pack|assorted|"
    r"\d{2,}\s*(cards?|card\s+lot|rares?|mythics?|foils?)|cards?\s+lot|unsorted)\b",
    re.IGNORECASE,
)


def is_bulk_lot_title(title: str) -> bool:
    return bool(BULK_LOT_TITLE_PATTERNS.search(title or ""))


def is_probable_single_card_listing(title: str) -> bool:
    """Stricter than not-bulk: exclude accessories, multi-card packs, repacks."""
    text = title or ""
    if is_bulk_lot_title(text) or is_non_mtg_listing(text):
        return False
    if re.search(r"\b\d+\s+rare\b", text, re.IGNORECASE):
        return False
    if re.search(r"\b\d{2,}\+?\s*cards?\b", text, re.IGNORECASE):
        return False
    if re.search(r"\b(bundles?|deck\s+upgrade|multiple\s+offers?|promo\s+foils?)\b", text, re.IGNORECASE):
        return False
    if re.search(r"^\(\d+\)", text):
        return False
    if re.search(r"\bset\s+\d{2,}\+?\b", text, re.IGNORECASE):
        return False
    if re.search(r"\|\s*single cards?\b", text, re.IGNORECASE):
        return False
    if re.search(r"\b(up to \d+% off|multiple offers?)\b", text, re.IGNORECASE):
        return False
    if re.search(r"\b(random cards?|different\s+\w+|non foil singles|prerelease kit|storage box)\b", text, re.IGNORECASE):
        return False
    if re.search(r"\b\d+\s+different\b", text, re.IGNORECASE):
        return False
    return True


def is_non_mtg_listing(title: str) -> bool:
    return bool(NON_MTG_TITLE_PATTERNS.search(title or ""))
