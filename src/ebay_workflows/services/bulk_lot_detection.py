from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .image_gate import assess_visible_card_regions
from .ocr_extract import extract_ocr_fields


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


def detect_lot_cards_from_image(
    image_path: str,
    crop_dir: str,
    *,
    ocr_engine: str = "pytesseract",
    tesseract_cmd: str | None = None,
    max_cards: int = 12,
    min_area_ratio: float = 0.008,
    min_region_score: float = 0.55,
    allow_full_frame_fallback: bool = False,
) -> list[DetectedLotCard]:
    """
    Detect multiple card-like regions in a bulk-lot photo and OCR each crop for a title.
    """
    gate = assess_visible_card_regions(
        image_path,
        crop_dir,
        max_regions=max_cards,
        min_area_ratio=min_area_ratio,
        min_region_score=min_region_score,
        allow_full_frame_fallback=allow_full_frame_fallback,
    )
    regions = gate.regions
    if not gate.has_visible_cards or not regions:
        return []

    detected: list[DetectedLotCard] = []
    for region in regions:
        crop_path = region.crop_path or image_path
        fields = extract_ocr_fields(crop_path, engine=ocr_engine, tesseract_cmd=tesseract_cmd)
        title_block = fields.get("title")
        if not title_block:
            continue
        title, conf = title_block
        if len(title.strip()) < 3:
            continue
        detected.append(
            DetectedLotCard(
                title=title.strip(),
                quantity=1,
                confidence=float(conf),
                bbox_x=region.bbox_x,
                bbox_y=region.bbox_y,
                bbox_w=region.bbox_w,
                bbox_h=region.bbox_h,
                crop_path=crop_path,
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
        }
        for card in cards
    ]
