from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import ScryfallCard
from .card_identifiers import ParsedCardIdentifiers, lookup_card_by_identifiers, merge_identifiers, parse_card_identifiers
from .embedding_index import EmbeddingMatch, index_exists, search_similar_cards
from .title_match import ScryfallTitleIndex, TitleMatchResult, best_card_match_for_text
from .zone_card_signals import best_title_from_fields, extract_card_zone_signals, identifiers_from_fields


def _faiss_score_for_card(matches: list[EmbeddingMatch], card_id: str) -> float | None:
    for match in matches:
        if match.scryfall_id == card_id:
            return match.score
    return None


def resolve_lot_crop_match(
    *,
    ocr_title: str,
    crop_path: str | None,
    title_index: ScryfallTitleIndex,
    set_collector_index: dict[tuple[str, str], str],
    card_by_id: dict[str, ScryfallCard],
    settings: Settings,
    extra_identifiers: ParsedCardIdentifiers | None = None,
    faiss_enabled: bool = True,
) -> tuple[ScryfallCard | None, float, dict[str, Any]]:
    """
    Match a lot crop using set/collector hints, title fuzzy match, and optional FAISS verification.
    """
    evidence: dict[str, Any] = {}
    faiss_path = crop_path
    zone_dir = str(Path(settings.image_cache_dir) / "lot_zones")

    if crop_path and Path(crop_path).is_file() and settings.card_zone_ocr_enabled:
        fields, _crops, zone_evidence = extract_card_zone_signals(crop_path, zone_dir, settings)
        evidence["zone_evidence"] = zone_evidence
        zone_title = best_title_from_fields(fields)
        if zone_title:
            ocr_title = zone_title
        faiss_path = zone_evidence.get("faiss_image_path", crop_path)
        zone_ids = identifiers_from_fields(fields)
        identifiers = merge_identifiers(extra_identifiers or ParsedCardIdentifiers(), zone_ids, parse_card_identifiers(ocr_title))
    else:
        identifiers = merge_identifiers(extra_identifiers or ParsedCardIdentifiers(), parse_card_identifiers(ocr_title))

    if identifiers.set_code or identifiers.collector_number:
        evidence["parsed_identifiers"] = {
            "set_code": identifiers.set_code,
            "collector_number": identifiers.collector_number,
        }

    title_result = best_card_match_for_text(
        ocr_title,
        title_index,
        set_collector_index,
        card_by_id,
        prefilter_size=settings.title_match_prefilter_size,
        score_cutoff=settings.title_match_score_cutoff,
        extra_identifiers=identifiers,
    )

    if title_result is not None and title_result.match_method == "set_collector":
        card = card_by_id.get(title_result.card_id)
        if card is not None:
            evidence["match_method"] = "set_collector"
            return card, title_result.score, evidence

    faiss_matches: list[EmbeddingMatch] = []
    if faiss_enabled and faiss_path and Path(faiss_path).is_file() and index_exists(settings.faiss_index_path):
        faiss_matches = search_similar_cards(faiss_path, settings, top_k=settings.faiss_top_k)
        if faiss_matches:
            evidence["faiss_matches"] = [
                {"scryfall_id": m.scryfall_id, "card_name": m.card_name, "score": m.score}
                for m in faiss_matches
            ]

    min_faiss = settings.image_evidence_min_faiss_score
    chosen: TitleMatchResult | None = title_result
    chosen_card: ScryfallCard | None = None
    chosen_score = 0.0

    if title_result is not None:
        chosen_card = card_by_id.get(title_result.card_id)
        chosen_score = title_result.score

    if faiss_matches:
        top = faiss_matches[0]
        top_score = float(top.score)
        evidence["faiss_top_scryfall_id"] = top.scryfall_id
        evidence["faiss_top_score"] = top_score

        if chosen_card is not None:
            matched_faiss = _faiss_score_for_card(faiss_matches, str(chosen_card.id))
            if matched_faiss is not None and matched_faiss >= min_faiss:
                evidence["faiss_verified"] = True
                chosen_score = max(chosen_score, min(1.0, matched_faiss))
            elif top_score >= min_faiss and str(chosen_card.id) != top.scryfall_id:
                faiss_card = card_by_id.get(top.scryfall_id)
                if faiss_card is not None:
                    evidence["faiss_override"] = True
                    evidence["title_match_rejected"] = {
                        "card_id": str(chosen_card.id),
                        "card_name": chosen_card.name,
                        "title_score": chosen_score,
                    }
                    chosen_card = faiss_card
                    chosen_score = top_score
                else:
                    evidence["faiss_verified"] = False
                    chosen_card = None
                    chosen_score = 0.0
            elif matched_faiss is None and top_score >= min_faiss:
                faiss_card = card_by_id.get(top.scryfall_id)
                if faiss_card is not None:
                    evidence["faiss_only_match"] = True
                    chosen_card = faiss_card
                    chosen_score = top_score
            else:
                evidence["faiss_verified"] = False
                chosen_card = None
                chosen_score = 0.0
        elif top_score >= min_faiss:
            faiss_card = card_by_id.get(top.scryfall_id)
            if faiss_card is not None:
                evidence["faiss_only_match"] = True
                chosen_card = faiss_card
                chosen_score = top_score

    if chosen_card is None:
        return None, 0.0, evidence

    if title_result is not None and str(chosen_card.id) == title_result.card_id:
        evidence["match_method"] = title_result.match_method
    elif evidence.get("faiss_only_match"):
        evidence["match_method"] = "faiss_crop"
    elif evidence.get("faiss_override"):
        evidence["match_method"] = "faiss_override"

    return chosen_card, chosen_score, evidence
