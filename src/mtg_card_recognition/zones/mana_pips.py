from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ManaDetection:
    colors: tuple[str, ...]
    generic_total: int
    confidence: float


# HSV centers for pip-like regions (OpenCV hue 0-180).
_COLOR_RANGES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "W": ((0, 0, 160), (180, 40, 255)),
    "U": ((90, 80, 80), (130, 255, 255)),
    "B": ((0, 0, 0), (180, 255, 70)),
    "R": ((0, 80, 80), (15, 255, 255)),
    "G": ((35, 60, 60), (85, 255, 255)),
}


def detect_mana_pips(mana_crop_path: str) -> ManaDetection:
    """
    Estimate colored and generic mana symbols in the mana-cost strip.
    Generic mana is counted from digit-like blobs; colors from HSV masks.
    """
    path = Path(mana_crop_path)
    if not path.is_file():
        return ManaDetection(colors=(), generic_total=0, confidence=0.0)

    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Mana detection requires opencv-python.") from exc

    image = cv2.imread(str(path))
    if image is None or image.size == 0:
        return ManaDetection(colors=(), generic_total=0, confidence=0.0)

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    colors_found: list[str] = []

    for color, (lower, upper) in _COLOR_RANGES.items():
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        ratio = float(cv2.countNonZero(mask)) / float(mask.size)
        if ratio > 0.015:
            colors_found.append(color)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    generic = 0
    h, w = gray.shape[:2]
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw < 4 or ch < 4:
            continue
        if cw > w * 0.45 or ch > h * 0.9:
            continue
        aspect = cw / max(ch, 1)
        if 0.4 <= aspect <= 1.2:
            generic += 1

    confidence = min(0.9, 0.25 + 0.15 * len(colors_found) + 0.05 * generic)
    return ManaDetection(
        colors=tuple(colors_found),
        generic_total=max(0, generic - len(colors_found)),
        confidence=confidence if colors_found or generic else 0.0,
    )
