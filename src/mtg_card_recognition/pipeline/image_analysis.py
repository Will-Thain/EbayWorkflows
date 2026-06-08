from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import RecognitionSettings
from ..ocr.extract import extract_ocr_fields
from ..zones.signals import extract_card_zone_signals


@dataclass(slots=True)
class RegionAnalysis:
    region: Any
    fields: dict[str, tuple[str, float]]
    embedding_matches: list[Any]
    zone_evidence: dict | None = None


@dataclass(slots=True)
class ImageAnalysisResult:
    listing_image_id: str
    listing_id: str
    skipped: bool
    skip_reason: str
    regions: list[RegionAnalysis]


def analyze_listing_regions(
    *,
    listing_image_id: str,
    listing_id: str,
    local_path: str,
    crop_dir: str,
    settings: RecognitionSettings,
    gate_regions: Callable[[str, str], Any],
    search_embedding: Callable[[str], list[Any]] | None = None,
) -> ImageAnalysisResult:
    """Run region gate, zone OCR, and optional embedding search on one listing image."""
    gate = gate_regions(local_path, crop_dir)
    if not gate.has_visible_cards:
        return ImageAnalysisResult(
            listing_image_id=listing_image_id,
            listing_id=listing_id,
            skipped=True,
            skip_reason=gate.reason,
            regions=[],
        )

    embedding_enabled = search_embedding is not None
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
        matches: list[Any] = []
        if embedding_enabled and faiss_path and search_embedding is not None:
            matches = search_embedding(faiss_path)
        if not fields and not matches and not zone_evidence:
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
