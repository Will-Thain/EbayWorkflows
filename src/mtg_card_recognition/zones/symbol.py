from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..config import RecognitionSettings

_TEMPLATE_CACHE: dict[str, dict[str, object]] = {}


def set_symbol_template_dir(settings: RecognitionSettings) -> Path:
    return Path(settings.image_cache_dir) / "set_symbol_templates"


def clear_set_symbol_template_cache() -> None:
    _TEMPLATE_CACHE.clear()


def _load_template_matrix(settings: RecognitionSettings) -> dict[str, object]:
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


def match_set_symbol(
    symbol_crop_path: str,
    settings: RecognitionSettings,
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
