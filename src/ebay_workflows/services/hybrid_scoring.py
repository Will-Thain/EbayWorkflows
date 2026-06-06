from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..config import Settings
from ..models import Listing, ListingCardCandidate
from .ev_guardrails import cap_ev_adjusted

# Versioned weights for v2_hybrid scoring.
HYBRID_WEIGHTS_V2 = {
    "title_match": Decimal("0.35"),
    "ocr": Decimal("0.25"),
    "embedding": Decimal("0.25"),
    "price_freshness": Decimal("0.15"),
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def hybrid_confidence_components(candidate: ListingCardCandidate) -> dict[str, float]:
    evidence: dict[str, Any] = dict(candidate.evidence_json or {})

    title_match = _clamp(float(candidate.match_score))
    ocr_block = evidence.get("ocr_verification") or {}
    ocr = _clamp(float(ocr_block.get("similarity", 0.0)))

    embedding = 0.0
    faiss_matches = evidence.get("faiss_matches") or []
    if faiss_matches:
        top = faiss_matches[0]
        top_score = _clamp(float(top.get("score", 0.0)))
        if candidate.scryfall_id and str(candidate.scryfall_id) == str(top.get("scryfall_id")):
            embedding = top_score
        else:
            embedding = top_score * 0.5

    price_freshness = 1.0 if evidence.get("cardmarket_price") else 0.0

    return {
        "title_match_confidence": title_match,
        "ocr_confidence": ocr,
        "embedding_match_confidence": embedding,
        "price_freshness_confidence": price_freshness,
    }


def composite_hybrid_confidence(components: dict[str, float]) -> float:
    weighted = (
        float(HYBRID_WEIGHTS_V2["title_match"]) * components["title_match_confidence"]
        + float(HYBRID_WEIGHTS_V2["ocr"]) * components["ocr_confidence"]
        + float(HYBRID_WEIGHTS_V2["embedding"]) * components["embedding_match_confidence"]
        + float(HYBRID_WEIGHTS_V2["price_freshness"]) * components["price_freshness_confidence"]
    )
    return _clamp(weighted)


def compute_listing_score_hybrid(
    candidates: list[ListingCardCandidate],
    listing: Listing,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if not candidates:
        listing_cost = Decimal(str(listing.price_amount)) + Decimal(str(listing.shipping_amount or 0))
        return {
            "ev_raw": -listing_cost,
            "confidence_score": Decimal("0"),
            "risk_score": Decimal("1"),
            "ev_adjusted": -listing_cost,
            "rank_value": -listing_cost,
            "explanation": {"reason": "no_candidates", "scoring_version": "v2_hybrid"},
        }

    top = sorted(candidates, key=lambda c: c.rank_position)[:3]
    gross_value = Decimal("0")
    confidence_total = Decimal("0")
    matched = 0
    matched_cards: list[dict] = []

    for candidate in top:
        cm = (candidate.evidence_json or {}).get("cardmarket_price")
        if not cm:
            continue
        price_amount = Decimal(str(cm.get("price_amount", 0)))
        components = hybrid_confidence_components(candidate)
        hybrid_confidence = composite_hybrid_confidence(components)
        candidate.confidence_score = hybrid_confidence

        gross_value += price_amount
        confidence_total += Decimal(str(hybrid_confidence))
        matched += 1
        matched_cards.append(
            {
                "scryfall_id": str(candidate.scryfall_id) if candidate.scryfall_id else None,
                "price_amount": float(price_amount),
                "hybrid_confidence": hybrid_confidence,
                "confidence_components": components,
            }
        )

    listing_cost = Decimal(str(listing.price_amount)) + Decimal(str(listing.shipping_amount or 0))
    ev_raw = gross_value - listing_cost
    confidence_score = confidence_total / Decimal(str(max(matched, 1)))
    risk_score = Decimal("1") - confidence_score
    ev_adjusted = ev_raw * confidence_score
    # Unpriced listings must not rank above scored lots (ev_adjusted=0 sorts above negatives).
    rank_value = ev_raw if matched == 0 else ev_adjusted
    ev_capped = False
    if matched > 0 and settings is not None:
        rank_value, ev_capped = cap_ev_adjusted(ev_adjusted, listing_cost, settings)

    explanation: dict[str, Any] = {
        "listing_cost": float(listing_cost),
        "gross_value": float(gross_value),
        "matched_cards": matched_cards,
        "weights": {k: float(v) for k, v in HYBRID_WEIGHTS_V2.items()},
        "scoring_version": "v2_hybrid",
    }
    if ev_capped:
        explanation["ev_capped"] = True
        explanation["ev_cap_multiple"] = settings.ev_max_listing_cost_multiple if settings else None

    return {
        "ev_raw": ev_raw,
        "confidence_score": confidence_score,
        "risk_score": risk_score,
        "ev_adjusted": ev_adjusted,
        "rank_value": rank_value,
        "explanation": explanation,
    }
