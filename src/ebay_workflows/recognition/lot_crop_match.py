"""Phase 6 per-crop match via v0.3 cascade."""

from __future__ import annotations

from typing import Any

from mtg_card_recognition.catalog.lookup import CatalogIndex
from mtg_card_recognition.identifiers import ParsedCardIdentifiers

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings
from ..models import ScryfallCard
from .region_crop_match import resolve_lot_crop_match as _resolve_lot_crop_match
from .title_match import ScryfallTitleIndex, TitleMatchResult
from ..recognition.embedding_index import index_exists, search_similar_cards


def resolve_lot_crop_match(
    *,
    ocr_title: str,
    crop_path: str | None,
    catalog: CatalogIndex,
    title_index: ScryfallTitleIndex,
    set_collector_index: dict[tuple[str, str], str],
    card_by_id: dict[str, ScryfallCard],
    settings: Settings,
    extra_identifiers: ParsedCardIdentifiers | None = None,
) -> tuple[ScryfallCard | None, float, dict[str, Any]]:
    recognition = coerce_recognition_settings(settings)
    search_fn = None
    if index_exists(settings.faiss_index_path):

        def _search(path: str):
            return search_similar_cards(path, settings, top_k=settings.faiss_top_k)

        search_fn = _search

    return _resolve_lot_crop_match(
        ocr_title=ocr_title,
        crop_path=crop_path,
        catalog=catalog,
        title_index=title_index,
        set_collector_index=set_collector_index,
        card_by_id=card_by_id,
        recognition=recognition,
        prefilter_size=settings.title_match_prefilter_size,
        score_cutoff=settings.title_match_score_cutoff,
        extra_identifiers=extra_identifiers,
        search_fn=search_fn,
    )


__all__ = ["TitleMatchResult", "resolve_lot_crop_match"]
