from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import RecognitionSettings
from .align import normalize_card_image, soft_resize_card_image


@dataclass(frozen=True, slots=True)
class ZoneRect:
    """Normalized bounding box within a card crop (0–1)."""

    x: float
    y: float
    w: float
    h: float


# Shared symbol zones on the type line / title bar.
_SYMBOL_ZONES: dict[str, ZoneRect] = {
    "set_symbol": ZoneRect(x=0.82, y=0.525, w=0.11, h=0.075),
    "mana_cost": ZoneRect(x=0.76, y=0.035, w=0.20, h=0.105),
}

STANDARD_MTG_ZONES: dict[str, ZoneRect] = {
    "name": ZoneRect(x=0.05, y=0.03, w=0.72, h=0.11),
    "art": ZoneRect(x=0.07, y=0.14, w=0.86, h=0.44),
    "type_line": ZoneRect(x=0.05, y=0.525, w=0.78, h=0.06),
    "bottom": ZoneRect(x=0.04, y=0.905, w=0.92, h=0.085),
    **_SYMBOL_ZONES,
}

OLD_FRAME_MTG_ZONES: dict[str, ZoneRect] = {
    "name": ZoneRect(x=0.08, y=0.05, w=0.68, h=0.10),
    "art": ZoneRect(x=0.10, y=0.17, w=0.80, h=0.42),
    "type_line": ZoneRect(x=0.08, y=0.54, w=0.74, h=0.06),
    "bottom": ZoneRect(x=0.06, y=0.895, w=0.88, h=0.09),
    "set_symbol": ZoneRect(x=0.80, y=0.535, w=0.12, h=0.07),
    "mana_cost": ZoneRect(x=0.74, y=0.05, w=0.20, h=0.10),
}

# Front face only when a DFC is photographed as one tall card.
DFC_FRONT_ZONES: dict[str, ZoneRect] = {
    "name": ZoneRect(x=0.05, y=0.02, w=0.72, h=0.07),
    "art": ZoneRect(x=0.07, y=0.10, w=0.86, h=0.30),
    "type_line": ZoneRect(x=0.05, y=0.41, w=0.78, h=0.05),
    "bottom": ZoneRect(x=0.04, y=0.46, w=0.92, h=0.04),
    "set_symbol": ZoneRect(x=0.82, y=0.41, w=0.11, h=0.05),
    "mana_cost": ZoneRect(x=0.76, y=0.025, w=0.20, h=0.07),
}


def layout_from_scryfall_payload(payload: dict[str, Any] | None) -> str | None:
    """Map Scryfall card JSON to a zone layout family when metadata is known."""
    if not payload:
        return None
    layout = str(payload.get("layout") or "").lower()
    frame = str(payload.get("frame") or "").lower()
    if layout in {"transform", "modal_dfc", "double_faced_token", "reversible_card"}:
        return "dfc_front"
    if frame in {"1993", "1997", "2003"} or payload.get("border_color") == "white" and frame == "2003":
        return "old"
    if layout in {"split", "adventure", "planar", "scheme", "vanguard"}:
        return "modern"
    return None


def detect_frame_layout(image) -> str:
    """
    Heuristic frame detector: modern (default), old border, or DFC front face.
    Expects a BGR image array.
    """
    height, width = image.shape[:2]
    if height <= 0 or width <= 0:
        return "modern"

    aspect = height / max(width, 1)
    if aspect > 1.42:
        return "dfc_front"

    import cv2  # type: ignore[import-not-found]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    top_band = gray[0 : max(1, int(height * 0.06)), :]
    border_band = gray[int(height * 0.02) : int(height * 0.10), int(width * 0.04) : int(width * 0.96)]
    center_art = gray[int(height * 0.20) : int(height * 0.55), int(width * 0.15) : int(width * 0.85)]

    top_mean = float(top_band.mean()) if top_band.size else 255.0
    border_mean = float(border_band.mean()) if border_band.size else 255.0
    art_std = float(center_art.std()) if center_art.size else 0.0

    if top_mean > 150 and border_mean > 130 and art_std < 55:
        return "old"
    return "modern"


def zones_for_layout(layout: str) -> dict[str, ZoneRect]:
    if layout == "old":
        return OLD_FRAME_MTG_ZONES
    if layout == "dfc_front":
        return DFC_FRONT_ZONES
    return STANDARD_MTG_ZONES


@dataclass(slots=True)
class CardZoneCrops:
    """Paths to sub-crops of a card image by layout zone."""

    card_path: str
    zone_dir: str
    aligned_path: str | None = None
    frame_layout: str = "modern"
    name_path: str | None = None
    art_path: str | None = None
    type_line_path: str | None = None
    bottom_path: str | None = None
    set_symbol_path: str | None = None
    mana_cost_path: str | None = None


def _crop_normalized(image, rect: ZoneRect, *, width: int, height: int):
    x0 = max(0, int(rect.x * width))
    y0 = max(0, int(rect.y * height))
    x1 = min(width, int((rect.x + rect.w) * width))
    y1 = min(height, int((rect.y + rect.h) * height))
    if x1 <= x0 or y1 <= y0:
        return None
    return image[y0:y1, x0:x1]


def _write_zones_from_image(
    image,
    *,
    zone_map: dict[str, ZoneRect],
    zone_dir: Path,
    file_stem: str,
    zone_names: tuple[str, ...],
) -> dict[str, str | None]:
    import cv2  # type: ignore[import-not-found]

    height, width = image.shape[:2]
    paths: dict[str, str | None] = {name: None for name in zone_names}
    for zone_name in zone_names:
        rect = zone_map.get(zone_name)
        if rect is None:
            continue
        crop = _crop_normalized(image, rect, width=width, height=height)
        if crop is None or crop.size == 0:
            continue
        out = zone_dir / f"{file_stem}_{zone_name}.jpg"
        cv2.imwrite(str(out), crop)
        paths[zone_name] = str(out)
    return paths


def prepare_card_for_zones(
    card_path: str,
    zone_dir: str,
    settings: RecognitionSettings,
    *,
    stem: str | None = None,
    layout_hint: str | None = None,
    scryfall_payload: dict[str, Any] | None = None,
) -> tuple[CardZoneCrops, dict[str, Any]]:
    """Align (optional), detect frame layout, and extract all zone crops."""
    path = Path(card_path)
    meta: dict[str, Any] = {}
    result = CardZoneCrops(card_path=str(path), zone_dir=zone_dir)
    if not path.is_file():
        return result, meta

    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Zone extraction requires opencv-python.") from exc

    working_path = str(path)
    if settings.card_zone_align_enabled:
        align_dir = Path(zone_dir) / "aligned"
        align_dir.mkdir(parents=True, exist_ok=True)
        file_stem = stem or hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        aligned_out = align_dir / f"{file_stem}_aligned.jpg"
        normalized, align_conf = normalize_card_image(working_path, str(aligned_out))
        if normalized:
            working_path = normalized
            result.aligned_path = normalized
            meta["align_confidence"] = align_conf
        else:
            soft_path, soft_conf = soft_resize_card_image(working_path, str(aligned_out))
            if soft_path:
                working_path = soft_path
                result.aligned_path = soft_path
                meta["align_confidence"] = soft_conf
                meta["align_fallback"] = "soft_resize"

    image = cv2.imread(working_path)
    if image is None:
        return result, meta

    scryfall_layout = layout_from_scryfall_payload(scryfall_payload)
    if layout_hint:
        layout = layout_hint
        meta["frame_layout_source"] = "hint"
    elif scryfall_layout:
        layout = scryfall_layout
        meta["frame_layout_source"] = "scryfall_payload"
    else:
        layout = detect_frame_layout(image)
        meta["frame_layout_source"] = "heuristic"
    result.frame_layout = layout
    meta["frame_layout"] = layout
    zone_map = zones_for_layout(layout)

    Path(zone_dir).mkdir(parents=True, exist_ok=True)
    file_stem = stem or hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    zone_names = ("name", "art", "type_line", "bottom", "set_symbol", "mana_cost")
    paths = _write_zones_from_image(
        image,
        zone_map=zone_map,
        zone_dir=Path(zone_dir),
        file_stem=file_stem,
        zone_names=zone_names,
    )

    result.name_path = paths.get("name")
    result.art_path = paths.get("art")
    result.type_line_path = paths.get("type_line")
    result.bottom_path = paths.get("bottom")
    result.set_symbol_path = paths.get("set_symbol")
    result.mana_cost_path = paths.get("mana_cost")
    return result, meta


def extract_zone_crops(
    card_path: str,
    zone_dir: str,
    *,
    zones: dict[str, ZoneRect] | None = None,
    stem: str | None = None,
) -> CardZoneCrops:
    """Legacy helper: extract zones without alignment or frame detection."""
    path = Path(card_path)
    result = CardZoneCrops(card_path=str(path), zone_dir=zone_dir)
    if not path.is_file():
        return result

    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Zone extraction requires opencv-python.") from exc

    image = cv2.imread(str(path))
    if image is None:
        return result

    zone_map = zones or STANDARD_MTG_ZONES
    Path(zone_dir).mkdir(parents=True, exist_ok=True)
    file_stem = stem or hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    paths = _write_zones_from_image(
        image,
        zone_map=zone_map,
        zone_dir=Path(zone_dir),
        file_stem=file_stem,
        zone_names=("name", "art", "type_line", "bottom", "set_symbol", "mana_cost"),
    )
    result.name_path = paths.get("name")
    result.art_path = paths.get("art")
    result.type_line_path = paths.get("type_line")
    result.bottom_path = paths.get("bottom")
    result.set_symbol_path = paths.get("set_symbol")
    result.mana_cost_path = paths.get("mana_cost")
    return result


def faiss_query_path(crops: CardZoneCrops, *, use_art_zone: bool) -> str:
    """Pick the image path used for embedding search."""
    if use_art_zone and crops.art_path and Path(crops.art_path).is_file():
        return crops.art_path
    if crops.aligned_path and Path(crops.aligned_path).is_file():
        return crops.aligned_path
    return crops.card_path


def extract_art_zone_from_card_image(
    full_image_path: str,
    output_path: str,
    *,
    align_enabled: bool = True,
) -> str | None:
    """Crop the art zone from a full card image for FAISS indexing (matches query domain)."""
    path = Path(full_image_path)
    out = Path(output_path)
    if not path.is_file():
        return None

    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Art zone extraction requires opencv-python.") from exc

    working_path = str(path)
    if align_enabled:
        align_out = out.with_name(f"{out.stem}_aligned.jpg")
        normalized, _conf = normalize_card_image(working_path, str(align_out))
        if normalized:
            working_path = normalized
        else:
            soft, _soft_conf = soft_resize_card_image(working_path, str(align_out))
            if soft:
                working_path = soft

    image = cv2.imread(working_path)
    if image is None:
        return None

    layout = detect_frame_layout(image)
    zone_map = zones_for_layout(layout)
    art_rect = zone_map.get("art")
    if art_rect is None:
        return None

    height, width = image.shape[:2]
    crop = _crop_normalized(image, art_rect, width=width, height=height)
    if crop is None or crop.size == 0:
        return None

    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), crop)
    return str(out)
