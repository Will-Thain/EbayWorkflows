from __future__ import annotations

import re
from pathlib import Path


def _normalize_confidence(text: str) -> float:
    cleaned = text.strip()
    if not cleaned:
        return 0.0
    return min(0.95, max(0.35, len(cleaned) / 40))


def extract_ocr_fields(image_path: str, engine: str = "pytesseract") -> dict[str, tuple[str, float]]:
    """
    Extract title-like text from a card crop.
    Returns field_type -> (raw_text, confidence).
    """
    path = Path(image_path)
    if not path.exists():
        return {}

    # PaddleOCR integration is planned; use Tesseract as interim implementation.
    if engine not in {"pytesseract", "paddleocr"}:
        raise ValueError(f"Unsupported OCR engine: {engine}")

    try:
        import cv2  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("OCR requires opencv-python and pytesseract.") from exc

    image = cv2.imread(str(path))
    if image is None:
        return {}

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    raw = pytesseract.image_to_string(thresh, config="--psm 6").strip()
    if not raw:
        return {}

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return {}

    title = lines[0]
    fields: dict[str, tuple[str, float]] = {
        "title": (title, _normalize_confidence(title)),
    }

    for line in lines[1:3]:
        set_match = re.search(r"\b([A-Z]{2,5})\b", line)
        if set_match and "set_code" not in fields:
            code = set_match.group(1)
            fields["set_code"] = (code, 0.6)
        number_match = re.search(r"\b(\d{1,4}[A-Z]?)\b", line)
        if number_match and "collector_number" not in fields:
            number = number_match.group(1)
            fields["collector_number"] = (number, 0.55)

    return fields
