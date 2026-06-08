from __future__ import annotations

from pathlib import Path

import pytest

from ebay_workflows.services.bulk_lot_detection import (
    detect_lot_cards_from_image,
    detected_lot_cards_to_payload,
)


@pytest.fixture
def bulk_lot_image(tmp_path: Path) -> Path:
    import cv2  # type: ignore[import-not-found]
    import numpy as np  # type: ignore[import-not-found]

    canvas = np.zeros((800, 1200, 3), dtype=np.uint8)
    cv2.rectangle(canvas, (80, 100), (280, 500), (230, 230, 230), -1)
    cv2.rectangle(canvas, (350, 120), (550, 520), (220, 220, 220), -1)
    cv2.rectangle(canvas, (650, 110), (850, 510), (210, 210, 210), -1)
    cv2.putText(canvas, "Bolt", (110, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    out = tmp_path / "lot.jpg"
    cv2.imwrite(str(out), canvas)
    return out


def test_detect_lot_cards_finds_multiple_regions(bulk_lot_image: Path, tmp_path: Path) -> None:
    from ebay_workflows.services.card_regions import detect_card_regions

    regions = detect_card_regions(str(bulk_lot_image), str(tmp_path / "crops"), max_regions=12, min_area_ratio=0.008)
    assert len(regions) >= 2

    pytest.importorskip("pytesseract")
    try:
        import pytesseract  # type: ignore[import-not-found]

        pytesseract.get_tesseract_version()
    except Exception:
        pytest.skip("Tesseract not installed")

    cards = detect_lot_cards_from_image(
        str(bulk_lot_image),
        str(tmp_path / "crops2"),
        ocr_engine="pytesseract",
    )
    payload = detected_lot_cards_to_payload(cards)
    assert isinstance(payload, list)
    if cards:
        assert "title" in payload[0]
        assert "bbox" in payload[0]
