from __future__ import annotations

import re
from typing import Any

_MANA_PIP_RE = re.compile(r"\{([WUBRGCPSXYZ/\d]+)\}")


def parse_mana_cost_string(mana_cost: str | None) -> frozenset[str]:
    """Extract WUBRG color pips from a Scryfall mana_cost string like '{2}{R}{R}'."""
    if not mana_cost:
        return frozenset()
    colors: set[str] = set()
    for token in _MANA_PIP_RE.findall(mana_cost.upper()):
        if token in {"W", "U", "B", "R", "G"}:
            colors.add(token)
    return frozenset(colors)


def scryfall_card_mana_colors(scryfall_card: Any) -> frozenset[str]:
    """Return colored mana pips for a Scryfall card from payload or oracle data."""
    payload = getattr(scryfall_card, "raw_payload_json", None) or {}
    if isinstance(payload, dict):
        mana_cost = payload.get("mana_cost")
        parsed = parse_mana_cost_string(mana_cost if isinstance(mana_cost, str) else None)
        if parsed:
            return parsed
        colors = payload.get("colors") or payload.get("color_identity") or []
        if isinstance(colors, list):
            return frozenset(str(c).upper() for c in colors if str(c).upper() in {"W", "U", "B", "R", "G"})
    return frozenset()
