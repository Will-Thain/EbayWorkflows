from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from .card_regions import CardRegion
from .embedding_index import EmbeddingMatch, index_exists, search_similar_cards
from .image_gate import assess_visible_card_regions
from .ocr_extract import extract_ocr_fields
from .zone_card_signals import extract_card_zone_signals


@dataclass(slots=True)
class RegionAnalysis:
    region: CardRegion
    fields: dict[str, tuple[str, float]]
    embedding_matches: list[EmbeddingMatch]
    zone_evidence: dict | None = None


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
    zone_dir = str(Path(crop_dir) / "zones")
    region_results: list[RegionAnalysis] = []
    for region in gate.regions:
        crop_path = region.crop_path or local_path
        zone_evidence: dict = {}
        if settings.card_zone_ocr_enabled:
            fields, _crops, zone_evidence = extract_card_zone_signals(crop_path, zone_dir, settings)
            faiss_path = zone_evidence.get("faiss_image_path", crop_path)
        else:
            fields = extract_ocr_fields(
                crop_path,
                engine=settings.ocr_engine,
                tesseract_cmd=settings.tesseract_cmd,
            )
            faiss_path = crop_path
        matches: list[EmbeddingMatch] = []
        if embedding_enabled and faiss_path:
            matches = search_similar_cards(faiss_path, settings, top_k=settings.faiss_top_k)
        if not fields and not matches:
            continue
        region_results.append(
            RegionAnalysis(
                region=region,
                fields=fields,
                embedding_matches=matches,
                zone_evidence=zone_evidence or None,
            )
        )

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
