from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import Settings
from .card_regions import CardRegion
from .embedding_index import EmbeddingMatch, index_exists, search_similar_cards
from .image_gate import assess_visible_card_regions
from .ocr_extract import extract_ocr_fields


@dataclass(slots=True)
class RegionAnalysis:
    region: CardRegion
    fields: dict[str, tuple[str, float]]
    embedding_matches: list[EmbeddingMatch]


@dataclass(slots=True)
class ImageAnalysisResult:
    listing_image_id: str
    listing_id: str
    skipped: bool
    skip_reason: str
    regions: list[RegionAnalysis]


def analyze_listing_image(
    *,
    listing_image_id: str,
    listing_id: str,
    local_path: str,
    crop_dir: str,
    settings: Settings,
    use_embedding: bool,
) -> ImageAnalysisResult:
    gate = assess_visible_card_regions(
        local_path,
        crop_dir,
        min_region_score=settings.image_min_region_score,
        allow_full_frame_fallback=settings.image_allow_full_frame_fallback,
    )
    if not gate.has_visible_cards:
        return ImageAnalysisResult(
            listing_image_id=listing_image_id,
            listing_id=listing_id,
            skipped=True,
            skip_reason=gate.reason,
            regions=[],
        )

    embedding_enabled = use_embedding and index_exists(settings.faiss_index_path)
    region_results: list[RegionAnalysis] = []
    for region in gate.regions:
        crop_path = region.crop_path or local_path
        fields = extract_ocr_fields(
            crop_path,
            engine=settings.ocr_engine,
            tesseract_cmd=settings.tesseract_cmd,
        )
        matches: list[EmbeddingMatch] = []
        if embedding_enabled and crop_path:
            matches = search_similar_cards(crop_path, settings, top_k=settings.faiss_top_k)
        if not fields and not matches:
            continue
        region_results.append(RegionAnalysis(region=region, fields=fields, embedding_matches=matches))

    if not region_results:
        return ImageAnalysisResult(
            listing_image_id=listing_image_id,
            listing_id=listing_id,
            skipped=True,
            skip_reason="no_usable_ocr_or_embedding",
            regions=[],
        )

    return ImageAnalysisResult(
        listing_image_id=listing_image_id,
        listing_id=listing_id,
        skipped=False,
        skip_reason="processed",
        regions=region_results,
    )
