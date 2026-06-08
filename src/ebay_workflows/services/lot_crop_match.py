"""Shim: bulk lot crop matching lives in mtg_card_recognition.pipeline."""

from __future__ import annotations

from typing import Any

from mtg_card_recognition.pipeline.lot_match import resolve_lot_crop_match as _resolve_lot_crop_match

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings
from ..models import ScryfallCard
from .card_identifiers import ParsedCardIdentifiers
from .embedding_index import index_exists, search_similar_cards
from .title_match import ScryfallTitleIndex, TitleMatchResult


def resolve_lot_crop_match(
    *,
    ocr_title: str,
    crop_path: str | None,
    title_index: ScryfallTitleIndex,
    set_collector_index: dict[tuple[str, str], str],
    card_by_id: dict[str, ScryfallCard],
    settings: Settings,
    extra_identifiers: ParsedCardIdentifiers | None = None,
    faiss_enabled: bool = True,
) -> tuple[ScryfallCard | None, float, dict[str, Any]]:
    return _resolve_lot_crop_match(
        ocr_title=ocr_title,
        crop_path=crop_path,
        title_index=title_index,
        set_collector_index=set_collector_index,
        card_by_id=card_by_id,
        settings=coerce_recognition_settings(settings),
        extra_identifiers=extra_identifiers,
        faiss_enabled=faiss_enabled,
        search_similar=lambda path: search_similar_cards(path, settings, top_k=settings.faiss_top_k),
        index_ready=lambda: index_exists(settings.faiss_index_path),
    )


__all__ = ["TitleMatchResult", "resolve_lot_crop_match"]
