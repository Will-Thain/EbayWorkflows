"""Phase 6 bulk-lot region detect + v0.3 cascade per crop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mtg_card_recognition.catalog.lookup import CatalogIndex
from mtg_card_recognition.config import RecognitionSettings
from mtg_card_recognition.embeddings.search import EmbeddingMatch
from mtg_card_recognition.pipeline.region import run_region_from_image
from mtg_card_recognition.zones.gate import assess_visible_card_regions
from mtg_card_recognition.zones.tier0_signals import tier0_input_from_region


@dataclass(slots=True)
class DetectedLotCard:
    title: str
    quantity: int
    confidence: float
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    crop_path: str | None
    set_code: str | None = None
    collector_number: str | None = None


def _display_title(result: Any) -> str:
    signals = result.signals
    if signals is None:
        return ""
    if signals.name_ocr:
        return str(signals.name_ocr).strip()
    bottom = signals.bottom_parsed
    if bottom and bottom.raw_text:
        return str(bottom.raw_text).strip()[:80]
    for proposal in result.proposals:
        if proposal.name:
            return str(proposal.name).strip()
    return ""


def _region_confidence(result: Any, region_score: float) -> float:
    if result.proposals:
        best = max(result.proposals, key=lambda p: p.corroboration_score)
        return max(region_score, float(best.corroboration_score or 0.0))
    if result.signals and result.signals.bottom_parsed:
        return max(region_score, float(result.signals.bottom_parsed.ocr_confidence or 0.0))
    return region_score


def detect_lot_cards_from_image(
    image_path: str,
    crop_dir: str,
    settings: RecognitionSettings,
    catalog: CatalogIndex,
    *,
    search_fn: Callable[[str], list[EmbeddingMatch]] | None = None,
    max_cards: int = 12,
    min_area_ratio: float = 0.008,
    min_region_score: float | None = None,
    allow_full_frame_fallback: bool = False,
) -> list[DetectedLotCard]:
    """Detect card regions and run the v0.3 cascade on each crop."""
    region_score = (
        settings.image_min_region_score if min_region_score is None else min_region_score
    )
    gate = assess_visible_card_regions(
        image_path,
        crop_dir,
        max_regions=max_cards,
        min_area_ratio=min_area_ratio,
        min_region_score=region_score,
        allow_full_frame_fallback=allow_full_frame_fallback,
    )
    if not gate.has_visible_cards or not gate.regions:
        return []

    zone_dir = str(Path(crop_dir) / "zones")
    detected: list[DetectedLotCard] = []

    for region in gate.regions:
        crop_path = region.crop_path or image_path
        tier0 = tier0_input_from_region(
            region,
            fallback_full_frame=allow_full_frame_fallback,
        )
        result = run_region_from_image(
            crop_path,
            catalog=catalog,
            settings=settings,
            tier0=tier0,
            zone_dir=zone_dir,
            search_fn=search_fn,
        )
        if result.skipped:
            continue

        title = _display_title(result)
        if not title or len(title) < 3:
            continue

        set_code: str | None = None
        collector_number: str | None = None
        if result.signals and result.signals.bottom_parsed:
            bottom = result.signals.bottom_parsed
            set_code = bottom.set_code
            collector_number = bottom.collector_number

        detected.append(
            DetectedLotCard(
                title=title,
                quantity=1,
                confidence=_region_confidence(result, region.score),
                bbox_x=region.bbox_x,
                bbox_y=region.bbox_y,
                bbox_w=region.bbox_w,
                bbox_h=region.bbox_h,
                crop_path=crop_path,
                set_code=set_code,
                collector_number=collector_number,
            )
        )

    return detected


def detected_lot_cards_to_payload(cards: list[DetectedLotCard]) -> list[dict[str, Any]]:
    return [
        {
            "title": card.title,
            "quantity": card.quantity,
            "confidence": card.confidence,
            "bbox": {
                "x": card.bbox_x,
                "y": card.bbox_y,
                "w": card.bbox_w,
                "h": card.bbox_h,
            },
            "crop_path": card.crop_path,
            "set_code": card.set_code,
            "collector_number": card.collector_number,
        }
        for card in cards
    ]
