"""Phase 6 bulk lot detection — delegates to recognition layer."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings
from .bulk_lot_detection import (
    DetectedLotCard,
    detect_lot_cards_from_image as _detect_lot_cards_from_image,
    detected_lot_cards_to_payload,
)
from .catalog_index import CatalogIndex

if TYPE_CHECKING:
    from .embedding_index import EmbeddingMatch

__all__ = [
    "DetectedLotCard",
    "detect_lot_cards_from_image",
    "detected_lot_cards_to_payload",
]


def detect_lot_cards_from_image(
    image_path: str,
    crop_dir: str,
    catalog: CatalogIndex,
    *,
    search_fn: Callable[[str], list[EmbeddingMatch]] | None = None,
    ocr_engine: str = "pytesseract",
    tesseract_cmd: str | None = None,
    max_cards: int = 12,
    min_area_ratio: float = 0.008,
    min_region_score: float = 0.55,
    allow_full_frame_fallback: bool = False,
    settings: Settings | None = None,
) -> list[DetectedLotCard]:
    if settings is not None:
        recognition = coerce_recognition_settings(settings)
    else:
        from ..adapters.recognition_settings import RecognitionSettings

        recognition = RecognitionSettings(
            ocr_engine=ocr_engine,
            tesseract_cmd=tesseract_cmd,
            image_min_region_score=min_region_score,
            image_allow_full_frame_fallback=allow_full_frame_fallback,
        )
    return _detect_lot_cards_from_image(
        image_path,
        crop_dir,
        recognition,
        catalog,
        search_fn=search_fn,
        max_cards=max_cards,
        min_area_ratio=min_area_ratio,
        min_region_score=min_region_score,
        allow_full_frame_fallback=allow_full_frame_fallback,
    )
