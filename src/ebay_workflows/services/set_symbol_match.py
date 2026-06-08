from __future__ import annotations

import httpx
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import ScryfallCard
from .card_align import normalize_card_image, soft_resize_card_image
from .card_zones import _crop_normalized, detect_frame_layout, zones_for_layout

_TEMPLATE_CACHE: dict[str, dict[str, object]] = {}


def set_symbol_template_dir(settings: Settings) -> Path:
    return Path(settings.image_cache_dir) / "set_symbol_templates"


def _download_file(url: str, dest: Path, timeout_ms: int) -> bool:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=timeout_ms / 1000.0) as client:
            response = client.get(url)
            response.raise_for_status()
            dest.write_bytes(response.content)
        return dest.is_file() and dest.stat().st_size > 0
    except httpx.HTTPError:
        return False


def _load_template_matrix(settings: Settings) -> dict[str, object]:
    import cv2  # type: ignore[import-not-found]
    import numpy as np  # type: ignore[import-not-found]

    cache_key = str(set_symbol_template_dir(settings).resolve())
    cached = _TEMPLATE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    template_dir = set_symbol_template_dir(settings)
    codes: list[str] = []
    vectors: list[np.ndarray] = []
    if template_dir.is_dir():
        for template_path in sorted(template_dir.glob("*.png")):
            if template_path.stem.startswith("_"):
                continue
            template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
            if template is None:
                continue
            if template.shape != (48, 48):
                template = cv2.resize(template, (48, 48), interpolation=cv2.INTER_AREA)
            flat = template.astype(np.float32).reshape(-1)
            norm = float(np.linalg.norm(flat))
            if norm > 0:
                flat = flat / norm
            codes.append(template_path.stem.upper())
            vectors.append(flat)

    matrix = np.vstack(vectors) if vectors else np.empty((0, 48 * 48), dtype=np.float32)
    payload: dict[str, object] = {"codes": codes, "matrix": matrix}
    _TEMPLATE_CACHE[cache_key] = payload
    return payload


def clear_set_symbol_template_cache() -> None:
    _TEMPLATE_CACHE.clear()


def build_set_symbol_templates(session: Session, settings: Settings) -> dict[str, int]:
    """Build one normalized set-symbol template per set from a reference Scryfall card image."""
    import cv2  # type: ignore[import-not-found]

    clear_set_symbol_template_cache()
    template_dir = set_symbol_template_dir(settings)
    template_dir.mkdir(parents=True, exist_ok=True)
    align_dir = template_dir / "_align"
    align_dir.mkdir(parents=True, exist_ok=True)

    rows = session.execute(
        select(ScryfallCard.set_code, ScryfallCard.image_normal)
        .where(ScryfallCard.set_code.is_not(None), ScryfallCard.image_normal.is_not(None))
        .order_by(ScryfallCard.set_code)
    ).all()

    seen: set[str] = set()
    built = 0
    skipped = 0

    for set_code, image_url in rows:
        code = (set_code or "").strip().upper()
        if not code or code in seen or not image_url:
            continue
        seen.add(code)

        raw_path = template_dir / f"{code.lower()}_ref.jpg"
        if not raw_path.is_file():
            if not _download_file(image_url, raw_path, settings.image_download_timeout_ms):
                skipped += 1
                continue

        aligned_path = align_dir / f"{code.lower()}_aligned.jpg"
        normalized, _conf = normalize_card_image(str(raw_path), str(aligned_path))
        working = normalized
        if not working:
            working, _soft_conf = soft_resize_card_image(str(raw_path), str(aligned_path))
        if not working:
            working = str(raw_path)
        image = cv2.imread(working)
        if image is None:
            skipped += 1
            continue

        layout = detect_frame_layout(image)
        zone_map = zones_for_layout(layout)
        symbol_rect = zone_map.get("set_symbol")
        if symbol_rect is None:
            skipped += 1
            continue

        height, width = image.shape[:2]
        crop = _crop_normalized(image, symbol_rect, width=width, height=height)
        if crop is None or crop.size == 0:
            skipped += 1
            continue

        resized = cv2.resize(crop, (48, 48), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(template_dir / f"{code.lower()}.png"), resized)
        built += 1

    clear_set_symbol_template_cache()
    return {"templates_built": built, "sets_seen": len(seen), "templates_skipped": skipped}


def match_set_symbol(
    symbol_crop_path: str,
    settings: Settings,
    *,
    min_score: float | None = None,
    set_code_hints: Iterable[str] | None = None,
) -> tuple[str | None, float]:
    """Match a set-symbol crop against cached templates via normalized dot product."""
    import cv2  # type: ignore[import-not-found]
    import numpy as np  # type: ignore[import-not-found]

    threshold = min_score if min_score is not None else settings.card_set_symbol_min_score
    path = Path(symbol_crop_path)
    if not path.is_file():
        return None, 0.0

    query = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if query is None or query.size == 0:
        return None, 0.0
    query = cv2.resize(query, (48, 48), interpolation=cv2.INTER_AREA)
    flat = query.astype(np.float32).reshape(-1)
    norm = float(np.linalg.norm(flat))
    if norm <= 0:
        return None, 0.0
    flat = flat / norm

    cache = _load_template_matrix(settings)
    codes: list[str] = cache["codes"]  # type: ignore[assignment]
    matrix: np.ndarray = cache["matrix"]  # type: ignore[assignment]
    if matrix.size == 0:
        return None, 0.0

    hints = {str(h).strip().upper() for h in (set_code_hints or []) if str(h).strip()}
    if hints:
        indices = [index for index, code in enumerate(codes) if code in hints]
        if indices:
            subset = matrix[indices]
            scores = subset @ flat
            best_pos = int(scores.argmax())
            best_score = float(scores[best_pos])
            best_code = codes[indices[best_pos]]
            if best_score >= threshold:
                return best_code, best_score
            return None, best_score

    scores = matrix @ flat
    best_pos = int(scores.argmax())
    best_score = float(scores[best_pos])
    best_code = codes[best_pos]
    if best_score < threshold:
        return None, best_score
    return best_code, best_score
