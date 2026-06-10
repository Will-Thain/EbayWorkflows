"""Per-listing verification winner selection (EbayWorkflows)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from mtg_card_recognition.config import RecognitionSettings
from .candidate_gate import (
    apply_image_evidence_gate,
    demote_image_verification,
    evaluate_image_verification,
    is_verified_candidate,
    verification_strength,
)


def select_pricing_candidate(candidates: list[Any]) -> Any | None:
    eligible = [
        candidate
        for candidate in sorted(candidates, key=lambda row: row.rank_position)
        if is_verified_candidate(candidate)
        and (candidate.evidence_json or {}).get("cardmarket_price")
    ]
    if not eligible:
        return None

    def sort_key(candidate: Any) -> tuple[int, float, int]:
        evidence = candidate.evidence_json or {}
        source = evidence.get("image_verification_source")
        return (
            -verification_strength(source if isinstance(source, str) else None),
            -float(candidate.match_score or 0.0),
            int(candidate.rank_position or 999),
        )

    return min(eligible, key=sort_key)


def apply_per_listing_verification_gates(
    candidates: list[Any],
    settings: RecognitionSettings,
) -> tuple[int, int]:
    by_listing: dict[Any, list[Any]] = defaultdict(list)
    for candidate in candidates:
        by_listing[candidate.listing_id].append(candidate)

    verified_total = 0
    gated_total = 0

    for group in by_listing.values():
        evaluations: list[tuple[int, float, int, Any, str | None]] = []
        for candidate in group:
            scryfall_card = getattr(candidate, "scryfall_card", None)
            scryfall_id = str(candidate.scryfall_id) if candidate.scryfall_id else None
            evidence = dict(candidate.evidence_json or {})
            ok, source, strength = evaluate_image_verification(
                evidence,
                scryfall_id,
                settings,
                scryfall_card=scryfall_card,
            )
            rank = int(getattr(candidate, "rank_position", 999) or 999)
            match_score = float(getattr(candidate, "match_score", 0.0) or 0.0)
            evaluations.append(
                (strength if ok else -1, match_score, -rank, candidate, source if ok else None)
            )

        winner_entry = max(evaluations, key=lambda row: (row[0], row[1], row[2]))
        winner = winner_entry[3]
        winner_source = winner_entry[4]

        for candidate in group:
            if candidate is winner and winner_source:
                evidence = dict(candidate.evidence_json or {})
                scryfall_id = str(candidate.scryfall_id) if candidate.scryfall_id else None
                scryfall_card = getattr(candidate, "scryfall_card", None)
                verified, source = evaluate_image_verification(
                    evidence,
                    scryfall_id,
                    settings,
                    scryfall_card=scryfall_card,
                )[:2]
                if verified:
                    apply_image_evidence_gate(candidate, settings)
                    verified_total += 1
                else:
                    demote_image_verification(candidate)
                    gated_total += 1
            else:
                demote_image_verification(candidate)
                gated_total += 1

    return verified_total, gated_total
