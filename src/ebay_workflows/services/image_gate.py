from __future__ import annotations

from dataclasses import dataclass

from .card_regions import CardRegion, detect_card_regions


@dataclass(slots=True)
class ImageGateResult:
    has_visible_cards: bool
    regions: list[CardRegion]
    reason: str


def assess_visible_card_regions(
    image_path: str,
    crop_dir: str,
    *,
    max_regions: int = 5,
    min_area_ratio: float = 0.02,
    min_region_score: float = 0.55,
    allow_full_frame_fallback: bool = False,
) -> ImageGateResult:
    """
    Return card-like regions that pass visibility heuristics.
    When no region passes, has_visible_cards is False and downstream OCR/embedding should be skipped.
    """
    regions = detect_card_regions(
        image_path,
        crop_dir,
        max_regions=max_regions,
        min_area_ratio=min_area_ratio,
        fallback_to_full_frame=allow_full_frame_fallback,
    )
    visible = [region for region in regions if region.score >= min_region_score and region.bbox_w * region.bbox_h >= 0.02]
    if visible:
        return ImageGateResult(has_visible_cards=True, regions=visible, reason="regions_detected")
    if regions and allow_full_frame_fallback:
        return ImageGateResult(has_visible_cards=True, regions=regions, reason="full_frame_fallback")
    if regions:
        return ImageGateResult(has_visible_cards=False, regions=[], reason="low_quality_regions")
    return ImageGateResult(has_visible_cards=False, regions=[], reason="no_regions")
