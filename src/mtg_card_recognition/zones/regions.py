from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CardRegion:
    """Normalized bounding box (0-1) and optional saved crop path."""

    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    score: float
    crop_path: str | None = None


def _full_frame_region(image_path: str) -> CardRegion:
    return CardRegion(bbox_x=0.0, bbox_y=0.0, bbox_w=1.0, bbox_h=1.0, score=0.5, crop_path=image_path)


def detect_card_regions(
    image_path: str,
    crop_dir: str,
    *,
    max_regions: int = 5,
    min_area_ratio: float = 0.02,
    fallback_to_full_frame: bool = True,
) -> list[CardRegion]:
    """
    Detect card-like rectangles with OpenCV contour filtering.
    Falls back to full-frame region when no candidate contours are found.
    """
    path = Path(image_path)
    if not path.exists():
        return []

    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Card region detection requires opencv-python.") from exc

    image = cv2.imread(str(path))
    if image is None:
        return []

    height, width = image.shape[:2]
    if height == 0 or width == 0:
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    image_area = float(width * height)
    candidates: list[tuple[float, int, int, int, int]] = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = float(w * h)
        if area < image_area * min_area_ratio:
            continue
        aspect = w / max(h, 1)
        # MTG cards are roughly portrait; allow some perspective skew.
        if aspect < 0.45 or aspect > 1.15:
            continue
        fill_ratio = area / image_area
        score = min(0.99, 0.4 + fill_ratio * 2.0)
        candidates.append((score, x, y, w, h))

    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        if fallback_to_full_frame:
            return [_full_frame_region(str(path))]
        return []

    Path(crop_dir).mkdir(parents=True, exist_ok=True)
    stem = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    regions: list[CardRegion] = []

    for index, (score, x, y, w, h) in enumerate(candidates[:max_regions]):
        crop = image[y : y + h, x : x + w]
        crop_path = Path(crop_dir) / f"{stem}_{index}.jpg"
        cv2.imwrite(str(crop_path), crop)
        regions.append(
            CardRegion(
                bbox_x=round(x / width, 4),
                bbox_y=round(y / height, 4),
                bbox_w=round(w / width, 4),
                bbox_h=round(h / height, 4),
                score=score,
                crop_path=str(crop_path),
            )
        )

    return regions
