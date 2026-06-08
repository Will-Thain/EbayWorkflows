from __future__ import annotations

from pathlib import Path

import pytest

from ebay_workflows.services.card_regions import detect_card_regions
from ebay_workflows.services.ocr_extract import extract_ocr_fields


@pytest.fixture
def card_like_image(tmp_path: Path) -> Path:
    import cv2  # type: ignore[import-not-found]
    import numpy as np  # type: ignore[import-not-found]

    canvas = np.zeros((600, 800, 3), dtype=np.uint8)
    cv2.rectangle(canvas, (250, 80), (550, 520), (240, 240, 240), -1)
    cv2.putText(canvas, "Lightning Bolt", (270, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    out = tmp_path / "card.jpg"
    cv2.imwrite(str(out), canvas)
    return out


def test_detect_card_regions_finds_portrait_region(card_like_image: Path, tmp_path: Path) -> None:
    regions = detect_card_regions(str(card_like_image), str(tmp_path / "crops"))
    assert len(regions) >= 1
    primary = regions[0]
    assert 0 <= primary.bbox_x <= 1
    assert primary.bbox_w > 0.1
    assert primary.crop_path is not None
    assert Path(primary.crop_path).exists()


def test_extract_ocr_fields_reads_title(card_like_image: Path) -> None:
    pytest.importorskip("pytesseract")
    try:
        import pytesseract  # type: ignore[import-not-found]

        pytesseract.get_tesseract_version()
    except Exception:
        pytest.skip("Tesseract binary not installed on this machine.")

    fields = extract_ocr_fields(str(card_like_image), engine="pytesseract")
    assert "title" in fields
    assert "lightning" in fields["title"][0].lower()
