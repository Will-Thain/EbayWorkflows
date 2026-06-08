from __future__ import annotations

from typing import Any

from ..config import RecognitionSettings
from ..identifiers import ParsedCardIdentifiers, merge_identifiers, parse_bottom_strip, parse_card_identifiers
from ..ocr.extract import _normalize_confidence, _ocr_image_path
from .layouts import CardZoneCrops, faiss_query_path, prepare_card_for_zones
from .mana_pips import detect_mana_pips
from .symbol import match_set_symbol


def compute_zones_available(
    evidence: dict[str, Any],
    crops: CardZoneCrops,
    settings: RecognitionSettings,
) -> bool:
    if not settings.card_zone_ocr_enabled:
        return False
    if evidence.get("fallback_full_card_ocr"):
        return False
    if settings.card_zone_align_enabled:
        align_conf = float(evidence.get("align_confidence", 0.0))
        if align_conf < settings.align_min_confidence and not evidence.get("align_fallback"):
            return False
    if not crops.bottom_path:
        return False
    bottom_parsed = evidence.get("bottom_parsed") or {}
    if not crops.name_path and not bottom_parsed.get("set_code"):
        return False
    return True


def extract_card_zone_signals(
    card_path: str,
    zone_dir: str,
    settings: RecognitionSettings,
) -> tuple[dict[str, tuple[str, float]], CardZoneCrops, dict[str, Any]]:
    """Align card, OCR key zones, match set symbol, detect mana pips."""
    evidence: dict[str, Any] = {"zone_ocr": True}
    if settings.card_zone_ocr_enabled:
        crops, prep_meta = prepare_card_for_zones(card_path, zone_dir, settings)
        evidence.update(prep_meta)
    else:
        from .layouts import extract_zone_crops

        crops = extract_zone_crops(card_path, zone_dir)

    fields: dict[str, tuple[str, float]] = {}

    if crops.name_path:
        name_text = _ocr_image_path(crops.name_path, psm=7, tesseract_cmd=settings.tesseract_cmd)
        if name_text:
            fields["title"] = (name_text.strip(), _normalize_confidence(name_text))
            evidence["name_ocr"] = name_text.strip()

    if crops.bottom_path:
        bottom_text = _ocr_image_path(crops.bottom_path, psm=6, tesseract_cmd=settings.tesseract_cmd)
        if bottom_text:
            bottom_ids = parse_bottom_strip(bottom_text)
            evidence["bottom_ocr"] = bottom_text.strip()
            evidence["bottom_parsed"] = {
                "set_code": bottom_ids.set_code,
                "collector_number": bottom_ids.collector_number,
            }
            if bottom_ids.set_code:
                fields["set_code"] = (bottom_ids.set_code, 0.75)
            if bottom_ids.collector_number:
                fields["collector_number"] = (bottom_ids.collector_number, 0.72)

    if crops.type_line_path:
        type_text = _ocr_image_path(crops.type_line_path, psm=7, tesseract_cmd=settings.tesseract_cmd)
        if type_text:
            fields["type_line"] = (type_text.strip(), _normalize_confidence(type_text))
            evidence["type_line_ocr"] = type_text.strip()

    if settings.card_set_symbol_match_enabled and crops.set_symbol_path:
        hints: list[str] = []
        set_block = fields.get("set_code")
        bottom_set = (evidence.get("bottom_parsed") or {}).get("set_code")
        if set_block:
            hints.append(set_block[0])
        if bottom_set:
            hints.append(str(bottom_set))
        set_code, symbol_score = match_set_symbol(
            crops.set_symbol_path,
            settings,
            set_code_hints=hints or None,
        )
        evidence["set_symbol_match"] = {"set_code": set_code, "score": symbol_score}
        if set_code:
            existing = fields.get("set_code")
            if existing is None or symbol_score > existing[1]:
                fields["set_code"] = (set_code, symbol_score)

    if settings.card_mana_cost_enabled and crops.mana_cost_path:
        mana = detect_mana_pips(crops.mana_cost_path)
        evidence["mana_cost"] = {
            "colors": list(mana.colors),
            "generic_total": mana.generic_total,
            "confidence": mana.confidence,
        }
        if mana.colors:
            fields["mana_colors"] = ("".join(mana.colors), mana.confidence)

    if not fields.get("title"):
        fallback = _ocr_image_path(card_path, psm=6, tesseract_cmd=settings.tesseract_cmd)
        if fallback:
            lines = [line.strip() for line in fallback.splitlines() if line.strip()]
            if lines:
                fields["title"] = (lines[0], _normalize_confidence(lines[0]))
                evidence["fallback_full_card_ocr"] = True
                merged = merge_identifiers(
                    parse_bottom_strip("\n".join(lines)),
                    parse_card_identifiers("\n".join(lines[1:3])),
                )
                if merged.set_code and "set_code" not in fields:
                    fields["set_code"] = (merged.set_code, 0.55)
                if merged.collector_number and "collector_number" not in fields:
                    fields["collector_number"] = (merged.collector_number, 0.55)

    evidence["zones_available"] = compute_zones_available(evidence, crops, settings)
    faiss_path = faiss_query_path(crops, use_art_zone=settings.card_zone_faiss_enabled)
    evidence["faiss_image_path"] = faiss_path
    evidence["used_art_zone_faiss"] = faiss_path != card_path
    return fields, crops, evidence


def best_title_from_fields(fields: dict[str, tuple[str, float]]) -> str:
    block = fields.get("title")
    return block[0].strip() if block else ""


def identifiers_from_fields(fields: dict[str, tuple[str, float]]) -> ParsedCardIdentifiers:
    set_block = fields.get("set_code")
    num_block = fields.get("collector_number")
    return ParsedCardIdentifiers(
        set_code=set_block[0] if set_block else None,
        collector_number=num_block[0] if num_block else None,
    )
