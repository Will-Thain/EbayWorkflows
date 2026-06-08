"""Shim: zone signal extraction lives in mtg_card_recognition."""

from __future__ import annotations

from mtg_card_recognition.zones import signals as _signals

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings

__all__ = [
    "best_title_from_fields",
    "extract_card_zone_signals",
    "identifiers_from_fields",
]


def extract_card_zone_signals(card_path: str, zone_dir: str, settings: Settings):
    return _signals.extract_card_zone_signals(
        card_path,
        zone_dir,
        coerce_recognition_settings(settings),
    )


def best_title_from_fields(fields):
    return _signals.best_title_from_fields(fields)


def identifiers_from_fields(fields):
    return _signals.identifiers_from_fields(fields)
