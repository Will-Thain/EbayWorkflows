"""eBay integration for set-symbol templates: DB iteration; match in library."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from mtg_card_recognition.catalog import PrintingRecord
from mtg_card_recognition.zones.symbol import (
    clear_set_symbol_template_cache,
    match_set_symbol as _match_set_symbol,
    set_symbol_template_dir as _set_symbol_template_dir,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings
from ..models import ScryfallCard
from .set_symbol_templates import build_set_symbol_templates_from_printings


def set_symbol_template_dir(settings: Settings) -> Path:
    return _set_symbol_template_dir(coerce_recognition_settings(settings))


def match_set_symbol(
    symbol_crop_path: str,
    settings: Settings,
    *,
    min_score: float | None = None,
    set_code_hints: Iterable[str] | None = None,
) -> tuple[str | None, float]:
    """Match a set-symbol crop against cached templates (delegates to mtg_card_recognition)."""
    return _match_set_symbol(
        symbol_crop_path,
        coerce_recognition_settings(settings),
        min_score=min_score,
        set_code_hints=set_code_hints,
    )


def build_set_symbol_templates(session: Session, settings: Settings) -> dict[str, int]:
    """Build one normalized set-symbol template per set from Postgres Scryfall rows."""
    rows = session.execute(
        select(ScryfallCard)
        .where(ScryfallCard.image_normal.isnot(None))
        .where(ScryfallCard.set_code.isnot(None))
        .order_by(ScryfallCard.set_code)
    ).scalars()
    printings = [PrintingRecord.from_mapping(card) for card in rows]
    return build_set_symbol_templates_from_printings(
        printings,
        coerce_recognition_settings(settings),
    )


__all__ = [
    "build_set_symbol_templates",
    "clear_set_symbol_template_cache",
    "match_set_symbol",
    "set_symbol_template_dir",
]
