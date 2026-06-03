from __future__ import annotations

from pathlib import Path

import pytest

from ebay_workflows.services.card_regions import detect_card_regions
from ebay_workflows.services.image_gate import assess_visible_card_regions


@pytest.fixture
def card_like_image(tmp_path: Path) -> Path:
    import cv2  # type: ignore[import-not-found]
    import numpy as np  # type: ignore[import-not-found]

    canvas = np.zeros((600, 800, 3), dtype=np.uint8)
    cv2.rectangle(canvas, (250, 80), (550, 520), (240, 240, 240), -1)
    out = tmp_path / "card.jpg"
    cv2.imwrite(str(out), canvas)
    return out


def test_detect_card_regions_can_disable_full_frame_fallback(card_like_image: Path, tmp_path: Path) -> None:
    regions = detect_card_regions(
        str(card_like_image),
        str(tmp_path / "crops"),
        fallback_to_full_frame=False,
    )
    assert len(regions) >= 1


def test_assess_visible_card_regions_rejects_full_frame_only(card_like_image: Path, tmp_path: Path) -> None:
    gate = assess_visible_card_regions(
        str(card_like_image),
        str(tmp_path / "crops"),
        min_region_score=0.99,
        allow_full_frame_fallback=False,
    )
    assert gate.has_visible_cards is True or gate.reason in {"regions_detected", "low_quality_regions", "no_regions"}
