from __future__ import annotations

import re

from ..config import Settings

_GRADE_PATTERN = re.compile(
    r"\b("
    r"near\s*mint|nm|mint|new|"
    r"light(?:ly)?\s*play(?:ed)?|lp|gd|good|"
    r"moderate(?:ly)?\s*play(?:ed)?|mp|"
    r"heavy(?:ily)?\s*play(?:ed)?|hp|poor|"
    r"damaged|dmg"
    r")\b",
    re.IGNORECASE,
)

_GRADE_ALIASES: dict[str, str] = {
    "near mint": "NM",
    "nearmint": "NM",
    "nm": "NM",
    "mint": "NM",
    "new": "NM",
    "light play": "LP",
    "lightly played": "LP",
    "lightly play": "LP",
    "lightplay": "LP",
    "lp": "LP",
    "gd": "LP",
    "good": "LP",
    "moderate play": "MP",
    "moderately played": "MP",
    "moderately play": "MP",
    "moderateplay": "MP",
    "mp": "MP",
    "heavy play": "HP",
    "heavily played": "HP",
    "heavily play": "HP",
    "heavyplay": "HP",
    "hp": "HP",
    "poor": "HP",
    "damaged": "DMG",
    "dmg": "DMG",
}


def parse_listing_condition(title: str, condition_text: str | None = None) -> str:
    """Return NM, LP, MP, HP, DMG, or UNSPECIFIED from listing metadata."""
    for source in (condition_text or "", title):
        if not source:
            continue
        match = _GRADE_PATTERN.search(source)
        if not match:
            continue
        normalized = match.group(1).lower().replace("-", " ").strip()
        normalized = re.sub(r"\s+", " ", normalized)
        grade = _GRADE_ALIASES.get(normalized)
        if grade:
            return grade
    return "UNSPECIFIED"


def condition_price_multiplier(grade: str, settings: Settings) -> float:
    """Scale Cardmarket trend/NM prices to the listing's stated condition."""
    mapping = {
        "NM": settings.cardmarket_condition_multiplier_nm,
        "LP": settings.cardmarket_condition_multiplier_lp,
        "MP": settings.cardmarket_condition_multiplier_mp,
        "HP": settings.cardmarket_condition_multiplier_hp,
        "DMG": settings.cardmarket_condition_multiplier_dmg,
        "UNSPECIFIED": settings.cardmarket_condition_multiplier_unspecified,
    }
    return mapping.get(grade, settings.cardmarket_condition_multiplier_unspecified)


def adjust_price_for_listing_condition(
    price_amount: float,
    *,
    title: str,
    condition_text: str | None,
    settings: Settings,
) -> tuple[float, str, float]:
    """Return adjusted price, parsed grade, and multiplier."""
    grade = parse_listing_condition(title, condition_text)
    multiplier = condition_price_multiplier(grade, settings)
    return round(price_amount * multiplier, 2), grade, multiplier
