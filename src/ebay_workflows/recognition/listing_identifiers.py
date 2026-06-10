"""Listing-title identifier parsing for Phase 2 / Phase 6 (workflow concern)."""

from __future__ import annotations

import re

from mtg_card_recognition.identifiers import (
    ParsedCardIdentifiers,
    normalize_collector_number,
    normalize_set_code,
)

_SET_CODE_RE = re.compile(r"\b([A-Z0-9]{2,5})\b")
_COLLECTOR_FRACTION_RE = re.compile(r"\b(\d{1,4}[A-Za-z]?)\s*/\s*\d{1,4}\b")
_COLLECTOR_AFTER_SET_RE = re.compile(
    r"\b([A-Z0-9]{2,5})[-\s#]+(\d{1,4}[A-Za-z]?)\b",
    re.IGNORECASE,
)
_STANDALONE_NUMBER_RE = re.compile(r"\b(\d{1,4}[A-Za-z]?)\b")

_NOISE_TOKENS = frozenset(
    {
        "mtg",
        "magic",
        "the",
        "gathering",
        "card",
        "cards",
        "foil",
        "foils",
        "holo",
        "lot",
        "bulk",
        "mixed",
        "english",
        "eng",
        "rare",
        "common",
        "uncommon",
        "mythic",
        "playset",
        "x4",
        "x3",
        "x2",
        "x1",
        "nm",
        "lp",
        "mp",
        "hp",
        "gd",
        "ex",
        "vg",
        "mint",
        "new",
        "used",
        "played",
        "light",
        "lightly",
        "moderate",
        "moderately",
        "heavy",
        "heavily",
        "damaged",
        "damage",
        "near",
        "good",
        "poor",
        "fair",
        "psa",
        "cgc",
        "bgs",
        "graded",
        "reverse",
        "promo",
        "full",
        "art",
        "borderless",
        "extended",
        "showcase",
        "etched",
        "non",
        "and",
        "for",
        "with",
        "from",
        "set",
        "edition",
    }
)


def _is_plausible_set_code(token: str) -> bool:
    lowered = token.lower()
    if lowered in _NOISE_TOKENS:
        return False
    if len(token) < 2 or len(token) > 5:
        return False
    if token.isdigit():
        return False
    return True


def merge_identifiers(*parts: ParsedCardIdentifiers) -> ParsedCardIdentifiers:
    set_code: str | None = None
    collector: str | None = None
    for part in parts:
        if part.set_code and not set_code:
            set_code = part.set_code
        if part.collector_number and not collector:
            collector = part.collector_number
        if set_code and collector:
            break
    return ParsedCardIdentifiers(set_code=set_code, collector_number=collector)


def parse_card_identifiers(text: str) -> ParsedCardIdentifiers:
    """Extract set code and collector number from listing titles or OCR text."""
    if not text or not text.strip():
        return ParsedCardIdentifiers()

    for match in _COLLECTOR_AFTER_SET_RE.finditer(text):
        set_code = normalize_set_code(match.group(1))
        collector = normalize_collector_number(match.group(2))
        if set_code and collector and _is_plausible_set_code(set_code):
            return ParsedCardIdentifiers(set_code=set_code, collector_number=collector)

    fraction = _COLLECTOR_FRACTION_RE.search(text)
    collector = normalize_collector_number(fraction.group(1)) if fraction else None

    set_code: str | None = None
    for match in _SET_CODE_RE.finditer(text.upper()):
        candidate = normalize_set_code(match.group(1))
        if candidate and _is_plausible_set_code(candidate):
            set_code = candidate
            break

    if collector is None:
        for match in _STANDALONE_NUMBER_RE.finditer(text):
            candidate = normalize_collector_number(match.group(1))
            if candidate and candidate not in _NOISE_TOKENS:
                collector = candidate
                break

    return ParsedCardIdentifiers(set_code=set_code, collector_number=collector)


def build_set_collector_index(
    cards: list[tuple[str, str | None, str | None]],
) -> dict[tuple[str, str], str]:
    """Map (set_code, collector_number) -> scryfall card id."""
    index: dict[tuple[str, str], str] = {}
    for card_id, set_code, collector_number in cards:
        normalized_set = normalize_set_code(set_code)
        normalized_collector = normalize_collector_number(collector_number)
        if not normalized_set or not normalized_collector:
            continue
        key = (normalized_set.lower(), normalized_collector)
        index[key] = card_id
    return index


def lookup_card_by_identifiers(
    identifiers: ParsedCardIdentifiers,
    set_collector_index: dict[tuple[str, str], str],
) -> str | None:
    set_code = normalize_set_code(identifiers.set_code)
    collector = normalize_collector_number(identifiers.collector_number)
    if not set_code or not collector:
        return None
    return set_collector_index.get((set_code.lower(), collector))
