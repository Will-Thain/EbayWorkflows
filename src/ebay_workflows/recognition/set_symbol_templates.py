"""Offline set-symbol template build from Scryfall printings (workflow concern)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import httpx

from mtg_card_recognition.catalog.printing import PrintingRecord
from mtg_card_recognition.config import RecognitionSettings
from mtg_card_recognition.zones.align import normalize_card_image, soft_resize_card_image
from mtg_card_recognition.zones.crops import _crop_normalized
from mtg_card_recognition.zones.layouts import (
    detect_frame_layout_from_image,
    layout_from_scryfall_payload,
    zones_for_layout,
)
from mtg_card_recognition.zones.symbol import (
    clear_set_symbol_template_cache,
    set_symbol_template_dir,
)


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


def build_set_symbol_template_from_image(
    set_code: str,
    image_path: str,
    settings: RecognitionSettings,
    *,
    scryfall_payload: dict | None = None,
    template_path: Path | None = None,
) -> bool:
    """Crop set symbol from a full card image and write a normalized 48x48 template PNG."""
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        return False

    code = set_code.strip().upper()
    if not code:
        return False

    out_path = template_path or (set_symbol_template_dir(settings) / f"{code.lower()}.png")
    if out_path.is_file():
        return False

    path = Path(image_path)
    if not path.is_file():
        return False

    template_dir = set_symbol_template_dir(settings)
    align_dir = template_dir / "_align"
    align_dir.mkdir(parents=True, exist_ok=True)
    aligned_path = align_dir / f"{code.lower()}_aligned.jpg"
    normalized, _conf = normalize_card_image(str(path), str(aligned_path))
    working = normalized
    if not working:
        working, _soft_conf = soft_resize_card_image(str(path), str(aligned_path))
    if not working:
        working = str(path)
    image = cv2.imread(working)
    if image is None:
        return False

    layout_hint = layout_from_scryfall_payload(scryfall_payload)
    layout = layout_hint or detect_frame_layout_from_image(image)
    zone_map = zones_for_layout(layout)
    symbol_rect = zone_map.get("set_symbol")
    if symbol_rect is None:
        return False

    height, width = image.shape[:2]
    crop = _crop_normalized(image, symbol_rect, width=width, height=height)
    if crop is None or crop.size == 0:
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    resized = cv2.resize(crop, (48, 48), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out_path), resized)
    return True


def build_set_symbol_templates_from_printings(
    printings: Iterable[PrintingRecord],
    settings: RecognitionSettings,
) -> dict[str, int]:
    """Build one set-symbol template per unique set from Scryfall-like printing rows."""
    clear_set_symbol_template_cache()
    template_dir = set_symbol_template_dir(settings)
    template_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = template_dir / "_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    built = 0
    skipped = 0

    for printing in printings:
        code = (printing.set_code or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)

        template_path = template_dir / f"{code.lower()}.png"
        if template_path.is_file():
            continue

        image_url = printing.image_normal
        if not image_url:
            skipped += 1
            continue

        raw_path = raw_dir / f"{code.lower()}.jpg"
        if not raw_path.is_file():
            if not _download_file(image_url, raw_path, settings.image_download_timeout_ms):
                skipped += 1
                continue

        if build_set_symbol_template_from_image(
            code,
            str(raw_path),
            settings,
            scryfall_payload=printing.raw_payload_json or None,
            template_path=template_path,
        ):
            built += 1
        else:
            skipped += 1

    clear_set_symbol_template_cache()
    return {"templates_built": built, "sets_seen": len(seen), "templates_skipped": skipped}
