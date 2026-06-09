"""Shim: core listing image analysis lives in mtg_card_recognition.pipeline."""

from __future__ import annotations

from mtg_card_recognition.pipeline.image_analysis import (
    ImageAnalysisResult,
    RegionAnalysis,
    analyze_listing_regions,
)

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings
from mtg_card_recognition.zones.gate import assess_visible_card_regions

from .embedding_index import EmbeddingMatch, index_exists, search_similar_cards


def analyze_listing_image(
    *,
    listing_image_id: str,
    listing_id: str,
    local_path: str,
    crop_dir: str,
    settings: Settings,
    use_embedding: bool,
) -> ImageAnalysisResult:
    embedding_enabled = use_embedding and index_exists(settings.faiss_index_path)

    def _search(path: str) -> list[EmbeddingMatch]:
        return search_similar_cards(path, settings, top_k=settings.faiss_top_k)

    return analyze_listing_regions(
        listing_image_id=listing_image_id,
        listing_id=listing_id,
        local_path=local_path,
        crop_dir=crop_dir,
        settings=coerce_recognition_settings(settings),
        gate_regions=lambda path, out_dir: assess_visible_card_regions(
            path,
            out_dir,
            min_region_score=settings.image_min_region_score,
            allow_full_frame_fallback=settings.image_allow_full_frame_fallback,
        ),
        search_embedding=_search if embedding_enabled else None,
    )


__all__ = [
    "ImageAnalysisResult",
    "RegionAnalysis",
    "analyze_listing_image",
]
