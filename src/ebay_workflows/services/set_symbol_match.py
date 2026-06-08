"""eBay integration for set-symbol templates: build stays here; match logic in package."""

from __future__ import annotations

import httpx
from pathlib import Path
from typing import Iterable

from mtg_card_recognition.zones.symbol import (
    clear_set_symbol_template_cache,
    match_set_symbol as _match_set_symbol,
    set_symbol_template_dir as _set_symbol_template_dir,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings
from ..models import ScryfallCard
from .card_align import normalize_card_image, soft_resize_card_image
from .card_zones import _crop_normalized, detect_frame_layout, zones_for_layout
from mtg_card_recognition.zones.layouts import layout_from_scryfall_payload


def set_symbol_template_dir(settings: Settings) -> Path:
    return _set_symbol_template_dir(coerce_recognition_settings(settings))


def match_set_symbol(
    symbol_crop_path: str,
    settings: Settings,
    *,
    min_score: float | None = None,
    set_code_hints: Iterable[str] | None = None,
) -> tuple[str | None, float]:
    """Match a set-symbol crop against cached templates (delegates to mtg_card_recognition)."""
    return _match_set_symbol(
        symbol_crop_path,
        coerce_recognition_settings(settings),
        min_score=min_score,
        set_code_hints=set_code_hints,
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


def build_set_symbol_templates(session: Session, settings: Settings) -> dict[str, int]:
    """Build one normalized set-symbol template per set from a reference Scryfall card image."""
    import cv2  # type: ignore[import-not-found]

    clear_set_symbol_template_cache()
    template_dir = set_symbol_template_dir(settings)
    template_dir.mkdir(parents=True, exist_ok=True)
    align_dir = template_dir / "_align"
    align_dir.mkdir(parents=True, exist_ok=True)

    rows = session.execute(
        select(ScryfallCard)
        .where(ScryfallCard.image_normal.isnot(None))
        .where(ScryfallCard.set_code.isnot(None))
        .order_by(ScryfallCard.set_code)
    ).scalars()

    seen: set[str] = set()
    built = 0
    skipped = 0

    for card in rows:
        code = (card.set_code or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)

        template_path = template_dir / f"{code.lower()}.png"
        if template_path.is_file():
            continue

        image_url = card.image_normal
        if not image_url:
            skipped += 1
            continue

        raw_path = template_dir / "_raw" / f"{code.lower()}.jpg"
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

        layout_hint = layout_from_scryfall_payload(card.raw_payload_json)
        layout = layout_hint or detect_frame_layout(image)
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
        cv2.imwrite(str(template_path), resized)
        built += 1

    clear_set_symbol_template_cache()
    return {"templates_built": built, "sets_seen": len(seen), "templates_skipped": skipped}


__all__ = [
    "build_set_symbol_templates",
    "clear_set_symbol_template_cache",
    "match_set_symbol",
    "set_symbol_template_dir",
]
