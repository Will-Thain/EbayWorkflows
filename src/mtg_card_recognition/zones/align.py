from __future__ import annotations

from pathlib import Path

CANONICAL_CARD_WIDTH = 488
CANONICAL_CARD_HEIGHT = 680


def _order_quad_points(points):
    import numpy as np  # type: ignore[import-not-found]

    pts = np.array(points, dtype="float32")
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    ordered = np.zeros((4, 2), dtype="float32")
    ordered[0] = pts[np.argmin(s)]
    ordered[2] = pts[np.argmax(s)]
    ordered[1] = pts[np.argmin(diff)]
    ordered[3] = pts[np.argmax(diff)]
    return ordered


def normalize_card_image(
    image_path: str,
    output_path: str,
    *,
    min_area_ratio: float = 0.15,
) -> tuple[str | None, float]:
    """
    Deskew a card crop to a canonical portrait size using contour perspective warp.
    Returns (output_path, confidence) or (None, 0.0) when alignment fails.
    """
    path = Path(image_path)
    out = Path(output_path)
    if not path.is_file():
        return None, 0.0

    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Card alignment requires opencv-python and numpy.") from exc

    image = cv2.imread(str(path))
    if image is None:
        return None, 0.0

    height, width = image.shape[:2]
    if height < 50 or width < 40:
        return None, 0.0

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, 0.0

    image_area = float(width * height)
    best_quad = None
    best_score = 0.0

    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
        area = cv2.contourArea(contour)
        if area < image_area * min_area_ratio:
            continue
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) != 4:
            continue
        x, y, w, h = cv2.boundingRect(approx)
        aspect = w / max(h, 1)
        if aspect < 0.45 or aspect > 1.2:
            continue
        fill = area / image_area
        score = min(0.99, 0.35 + fill)
        if score > best_score:
            best_score = score
            best_quad = approx.reshape(4, 2)

    if best_quad is None:
        return soft_resize_card_image(str(path), str(out))

    src = _order_quad_points(best_quad)
    dst = np.array(
        [
            [0, 0],
            [CANONICAL_CARD_WIDTH - 1, 0],
            [CANONICAL_CARD_WIDTH - 1, CANONICAL_CARD_HEIGHT - 1],
            [0, CANONICAL_CARD_HEIGHT - 1],
        ],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(image, matrix, (CANONICAL_CARD_WIDTH, CANONICAL_CARD_HEIGHT))
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), warped)
    return str(out), best_score


def soft_resize_card_image(
    image_path: str,
    output_path: str,
    *,
    min_confidence: float = 0.35,
) -> tuple[str | None, float]:
    """
    Fallback alignment: resize to canonical card aspect when perspective warp fails.
    """
    path = Path(image_path)
    out = Path(output_path)
    if not path.is_file():
        return None, 0.0

    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Card alignment requires opencv-python.") from exc

    image = cv2.imread(str(path))
    if image is None:
        return None, 0.0

    height, width = image.shape[:2]
    if height < 40 or width < 30:
        return None, 0.0

    target_aspect = CANONICAL_CARD_WIDTH / CANONICAL_CARD_HEIGHT
    aspect = width / max(height, 1)
    if aspect > target_aspect:
        new_w = width
        new_h = max(1, int(width / target_aspect))
    else:
        new_h = height
        new_w = max(1, int(height * target_aspect))

    if new_h > height:
        pad = new_h - height
        top = pad // 2
        image = cv2.copyMakeBorder(image, top, pad - top, 0, 0, cv2.BORDER_REPLICATE)
    elif new_w > width:
        pad = new_w - width
        left = pad // 2
        image = cv2.copyMakeBorder(image, 0, 0, left, pad - left, cv2.BORDER_REPLICATE)

    resized = cv2.resize(image, (CANONICAL_CARD_WIDTH, CANONICAL_CARD_HEIGHT), interpolation=cv2.INTER_AREA)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), resized)
    return str(out), min_confidence
