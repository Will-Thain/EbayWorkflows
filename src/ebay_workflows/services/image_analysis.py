"""Phase 5 listing image analysis via mtg-card-recognition v0.3 cascade."""

from __future__ import annotations

from typing import Any

from mtg_card_recognition.embeddings.search import EmbeddingMatch
from mtg_card_recognition.pipeline.image_analysis import (
    ImageAnalysisResult,
    analyze_listing_image as _analyze_listing_image,
)

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings
from ..recognition.catalog_index import catalog_from_scryfall_rows, sidecar_from_catalog
from .embedding_index import index_exists, search_similar_cards


def analyze_listing_image(
    *,
    listing_image_id: str,
    listing_id: str,
    local_path: str,
    crop_dir: str,
    settings: Settings,
    use_embedding: bool,
    scryfall_cards: list[Any] | None = None,
    listing_title: str | None = None,
) -> ImageAnalysisResult:
    """Run Tier 0 gate + full cascade for one listing image."""
    recognition = coerce_recognition_settings(settings)
    cards = scryfall_cards or []
    catalog = catalog_from_scryfall_rows(cards)
    sidecar = sidecar_from_catalog(catalog) if cards else None

    embedding_enabled = use_embedding and index_exists(settings.faiss_index_path)

    def _search(path: str) -> list[EmbeddingMatch]:
        return search_similar_cards(
            path,
            recognition,
            top_k=recognition.faiss_global_k_prime,
        )

    return _analyze_listing_image(
        listing_image_id=listing_image_id,
        listing_id=listing_id,
        local_path=local_path,
        crop_dir=crop_dir,
        catalog=catalog,
        settings=recognition,
        sidecar=sidecar,
        listing_title=listing_title,
        search_fn=_search if embedding_enabled else None,
    )


__all__ = [
    "ImageAnalysisResult",
    "analyze_listing_image",
]
