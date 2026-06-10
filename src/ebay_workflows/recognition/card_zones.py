"""eBay adapter: zone crop prep with Settings → RecognitionSettings."""

from __future__ import annotations

from mtg_card_recognition.zones import layouts as _layouts

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings


def prepare_card_for_zones(
    card_path: str,
    zone_dir: str,
    settings: Settings,
    *,
    stem: str | None = None,
    layout_hint: str | None = None,
    scryfall_payload: dict | None = None,
):
    return _layouts.prepare_card_for_zones(
        card_path,
        zone_dir,
        coerce_recognition_settings(settings),
        stem=stem,
        layout_hint=layout_hint,
        scryfall_payload=scryfall_payload,
    )
