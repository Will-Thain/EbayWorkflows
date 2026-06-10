"""Five-agent expert panel review for one listing after a sample Phase 5 run."""
from __future__ import annotations

import argparse
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import cast, func, select, String

from ebay_workflows.config import Settings
from ebay_workflows.db import build_session_factory
from ebay_workflows.models import ImageDetection, Listing, ListingCardCandidate, ListingImage
from ebay_workflows.operations.listing_filters import (
    is_bulk_lot_title,
    is_non_mtg_listing,
    is_probable_single_card_listing,
)

SUBSTITUTE_NAME_RE = re.compile(r"substitute", re.IGNORECASE)
PSA_SLAB_RE = re.compile(r"\bPSA\b|\bBGS\b|\bslab\b", re.IGNORECASE)
GARBAGE_NAME_RE = re.compile(r"^(OO|i|a|—|-|\.)$", re.IGNORECASE)


@dataclass(slots=True)
class ExpertComment:
    agent: int
    agent_name: str
    code: str
    priority: str
    issue: str
    recommendation: str
    vote: str  # ACTION | DEFER | REJECT | APPROVE


@dataclass(slots=True)
class ExpertPanelVerdict:
    listing_id: str
    title: str
    run_metrics: dict[str, Any]
    comments: list[ExpertComment] = field(default_factory=list)
    consensus: str = "APPROVE"
    p0_actions: list[str] = field(default_factory=list)
    expected_behavior: str = ""
    actual_behavior: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "comments": [asdict(c) for c in self.comments],
        }


def _resolve_listing_id(session, listing_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(listing_id)
    except ValueError:
        row = session.execute(
            select(Listing.id).where(cast(Listing.id, String).like(f"{listing_id}%"))
        ).first()
        if row is None:
            raise SystemExit(f"Listing not found: {listing_id}")
        return row[0]


def _collect_listing_evidence(session, listing_id: uuid.UUID) -> dict[str, Any]:
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise SystemExit(f"Listing not found: {listing_id}")

    images = list(
        session.execute(select(ListingImage).where(ListingImage.listing_id == listing_id)).scalars().all()
    )
    region_count = int(
        session.execute(
            select(func.count())
            .select_from(ImageDetection)
            .join(ListingImage)
            .where(
                ListingImage.listing_id == listing_id,
                ImageDetection.detection_type == "card_region",
            )
        ).scalar_one()
    )

    candidates = list(
        session.execute(
            select(ListingCardCandidate).where(ListingCardCandidate.listing_id == listing_id)
        ).scalars().all()
    )

    candidate_snapshots: list[dict[str, Any]] = []
    verified_count = 0
    pricing_eligible = 0
    gate_counts: dict[str, int] = {}
    substitute_in_faiss = 0
    bottom_parsed_with_ids_count = 0
    bottom_parsed_key_count = 0
    bottom_ocr_empty_count = 0
    has_zone_evidence = False
    degraded_regions = 0
    symbol_only_verify_risk = 0

    for cand in candidates:
        ev = cand.evidence_json or {}
        gate = str(ev.get("gate_status") or "none")
        gate_counts[gate] = gate_counts.get(gate, 0) + 1
        if ev.get("image_verified"):
            verified_count += 1
            source = ev.get("image_verification_source") or ev.get("verification_source")
            if source == "set_symbol":
                symbol_only_verify_risk += 1
        if ev.get("pricing_eligible"):
            pricing_eligible += 1

        zone = ev.get("zone_evidence") or {}
        if zone:
            has_zone_evidence = True
        if zone.get("degraded_path"):
            degraded_regions += 1
        bottom_raw = zone.get("bottom_parsed")
        if isinstance(bottom_raw, dict):
            bottom_parsed_key_count += 1
            if bottom_raw.get("set_code") or bottom_raw.get("collector_number"):
                bottom_parsed_with_ids_count += 1
            elif not (bottom_raw.get("raw_text") or "").strip():
                bottom_ocr_empty_count += 1

        faiss_top = zone.get("faiss_top") or ev.get("faiss_matches") or []
        for hit in faiss_top if isinstance(faiss_top, list) else []:
            name = str(hit.get("card_name") or hit.get("name") or "")
            if SUBSTITUTE_NAME_RE.search(name):
                substitute_in_faiss += 1

        candidate_snapshots.append(
            {
                "rank": cand.rank_position,
                "source_method": cand.source_method,
                "match_score": float(cand.match_score or 0),
                "gate_status": gate,
                "gate_fail_reason": ev.get("gate_fail_reason"),
                "image_verified": ev.get("image_verified"),
                "verification_source": ev.get("image_verification_source"),
                "name_ocr_quality": zone.get("name_ocr_quality"),
                "align_confidence": zone.get("align_confidence"),
                "symbol_match": zone.get("symbol_match") or zone.get("set_symbol_match"),
            }
        )

    return {
        "listing": listing,
        "images": len(images),
        "region_count": int(region_count),
        "candidates": len(candidates),
        "verified_count": verified_count,
        "pricing_eligible": pricing_eligible,
        "gate_counts": gate_counts,
        "substitute_in_faiss": substitute_in_faiss,
        "bottom_parsed_with_ids_count": bottom_parsed_with_ids_count,
        "bottom_parsed_key_count": bottom_parsed_key_count,
        "bottom_ocr_empty_count": bottom_ocr_empty_count,
        "has_zone_evidence": has_zone_evidence,
        "degraded_regions": degraded_regions,
        "symbol_only_verify_risk": symbol_only_verify_risk,
        "candidate_snapshots": candidate_snapshots,
    }


def review_listing(
    session,
    listing_id: uuid.UUID,
    *,
    run_metrics: dict[str, Any] | None = None,
) -> ExpertPanelVerdict:
    data = _collect_listing_evidence(session, listing_id)
    listing: Listing = data["listing"]
    metrics = run_metrics or {}
    comments: list[ExpertComment] = []

    title = listing.title or ""
    regions_run = int(metrics.get("regions", data["region_count"]))
    verified_run = int(metrics.get("verified", data["verified_count"]))

    expected_parts: list[str] = []
    actual_parts: list[str] = []

    # --- Agent 1: CV/OCR ---
    if regions_run == 0 and data["images"] > 0:
        comments.append(
            ExpertComment(
                1,
                "CV/OCR",
                "E1-REGIONS",
                "P0",
                "Images present but zero card regions detected",
                "Tier 0b SKIP or improve detector; exclude store-picker listings from singles sample",
                "ACTION",
            )
        )
    if (
        data["region_count"] > 0
        and data["has_zone_evidence"]
        and data["bottom_parsed_key_count"] == 0
    ):
        comments.append(
            ExpertComment(
                1,
                "CV/OCR",
                "E1-BOTTOM-MISSING",
                "P0",
                "zone_evidence present but bottom_parsed key missing (P0-3 regression)",
                "Ensure cascade signals.to_dict() attaches bottom_parsed on candidate sync",
                "ACTION",
            )
        )
    elif (
        data["region_count"] > 0
        and data["bottom_parsed_key_count"] > 0
        and data["bottom_parsed_with_ids_count"] == 0
    ):
        comments.append(
            ExpertComment(
                1,
                "CV/OCR",
                "E1-BOTTOM-OCR",
                "P1",
                "bottom_parsed persisted but set/collector null (OCR parse empty)",
                "Tune bottom zone DPI/PSM; exclude slabs from verify tuning sample",
                "DEFER",
            )
        )
    if data["degraded_regions"] > 0 and PSA_SLAB_RE.search(title):
        comments.append(
            ExpertComment(
                1,
                "CV/OCR",
                "E1-SLAB",
                "P1",
                "PSA/slab listing → degraded_path expected",
                "DEFER verify on slabs; prefer raw NM scans in sample set",
                "DEFER",
            )
        )
    for snap in data["candidate_snapshots"]:
        sym = snap.get("symbol_match") or {}
        if sym.get("score", 0) >= 0.9 and sym.get("weak") and not snap.get("image_verified"):
            comments.append(
                ExpertComment(
                    1,
                    "CV/OCR",
                    "E1-SYMBOL-WEAK",
                    "P1",
                    f"Strong symbol match marked weak (rank {snap['rank']})",
                    "Correct: symbol must not verify alone on degraded path",
                    "APPROVE",
                )
            )
            break

    # --- Agent 2: IR ---
    if data["substitute_in_faiss"] > 0:
        comments.append(
            ExpertComment(
                2,
                "IR/Embeddings",
                "E2-SUBSTITUTE",
                "P0",
                f"FAISS top hits include Substitute Card ({data['substitute_in_faiss']} refs)",
                "Confirm substitute filter + sidecar index; veto before attach if still leaking",
                "ACTION",
            )
        )
    else:
        comments.append(
            ExpertComment(
                2,
                "IR/Embeddings",
                "E2-FAISS",
                "P2",
                "No substitute oracle in visible FAISS tops",
                "Continue monitoring faiss_substitute_top1_rate",
                "APPROVE",
            )
        )

    # --- Agent 3: Domain ---
    if not is_probable_single_card_listing(title):
        comments.append(
            ExpertComment(
                3,
                "MTG Domain",
                "E3-SAMPLE",
                "P0",
                "Listing should not be in singles-only sample",
                "Tighten is_probable_single_card_listing filter",
                "ACTION",
            )
        )
    if is_non_mtg_listing(title):
        comments.append(
            ExpertComment(
                3,
                "MTG Domain",
                "E3-TCG",
                "P0",
                "Non-MTG title in MTG pipeline",
                "Tier 0b TCG mismatch SKIP",
                "ACTION",
            )
        )
    if is_bulk_lot_title(title):
        comments.append(
            ExpertComment(
                3,
                "MTG Domain",
                "E3-BULK",
                "P0",
                "Bulk lot title in singles sample",
                "Route to Phase 6; skip Phase 2 title pricing",
                "ACTION",
            )
        )

    # --- Agent 4: Systems ---
    if data["candidates"] == 0 and int(metrics.get("regions", 0)) > 0:
        comments.append(
            ExpertComment(
                4,
                "Systems",
                "E4-NOCAND",
                "P0",
                "Regions detected but no title-match candidates (Phase 2 not run for listing)",
                "Run phase2-match-title for this listing before Phase 5 validation",
                "ACTION",
            )
        )
    elif data["candidates"] > 10:
        comments.append(
            ExpertComment(
                4,
                "Systems",
                "E4-CAPS",
                "P0",
                f"High candidate count ({data['candidates']}) for one listing",
                "Enforce panel v2 caps <=5/listing",
                "ACTION",
            )
        )
    comments.append(
        ExpertComment(
            4,
            "Systems",
            "E4-METRICS",
            "P2",
            f"Run metrics: regions={regions_run} gated={metrics.get('gated', '?')}",
            "Emit proposals_raw/post_veto/verified per run (Tier 7 metrics)",
            "DEFER",
        )
    )

    # --- Agent 5: Trust ---
    if data["verified_count"] > 0:
        comments.append(
            ExpertComment(
                5,
                "Trust/EV",
                "E5-VERIFY",
                "P0",
                f"image_verified=true on {data['verified_count']} candidate(s)",
                "Audit visual ground truth; set_symbol-only must not price",
                "REJECT",
            )
        )
    elif verified_run == 0 and regions_run > 0:
        comments.append(
            ExpertComment(
                5,
                "Trust/EV",
                "E5-OK",
                "P2",
                "No false verify on this run",
                "Expected under strict gate until set_collector path works",
                "APPROVE",
            )
        )
    if data["pricing_eligible"] > 0 and data["verified_count"] == 0:
        comments.append(
            ExpertComment(
                5,
                "Trust/EV",
                "E5-PRICE",
                "P1",
                "pricing_eligible without image_verified",
                "Title-only pricing OK only for true singles; gate should clear on Phase 5",
                "DEFER",
            )
        )

    # Expected vs actual summary
    if PSA_SLAB_RE.search(title):
        expected_parts.append("0 verified (slab photo); regions optional")
    elif is_probable_single_card_listing(title):
        expected_parts.append(">=1 region; cascade proposals; 0 verify until set_collector")
    else:
        expected_parts.append("SKIP or Phase 6 route; not singles sample")

    actual_parts.append(
        f"regions={data['region_count']} candidates={data['candidates']} "
        f"verified={data['verified_count']} gates={data['gate_counts']}"
    )

    p0_actions = [c.recommendation for c in comments if c.priority == "P0" and c.vote == "ACTION"]
    reject_count = sum(1 for c in comments if c.vote == "REJECT")
    action_count = sum(1 for c in comments if c.vote == "ACTION")

    if reject_count > 0 or action_count >= 2:
        consensus = "APPROVE_WITH_AMENDMENTS"
    elif action_count == 1:
        consensus = "APPROVE_WITH_AMENDMENTS"
    else:
        consensus = "APPROVE"

    return ExpertPanelVerdict(
        listing_id=str(listing_id),
        title=title,
        run_metrics=metrics,
        comments=comments,
        consensus=consensus,
        p0_actions=p0_actions,
        expected_behavior="; ".join(expected_parts),
        actual_behavior="; ".join(actual_parts),
    )


def print_verdict(verdict: ExpertPanelVerdict) -> None:
    print(f"\n--- Expert panel (5 agents) ---")
    print(f"Consensus: {verdict.consensus}")
    print(f"Expected: {verdict.expected_behavior}")
    print(f"Actual:   {verdict.actual_behavior}")
    for comment in verdict.comments:
        print(
            f"  [A{comment.agent} {comment.agent_name}] {comment.priority} {comment.code} "
            f"{comment.vote}: {comment.issue}"
        )
        print(f"      -> {comment.recommendation}")
    if verdict.p0_actions:
        print(f"P0 actions: {len(verdict.p0_actions)}")
        for action in verdict.p0_actions[:3]:
            print(f"  - {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Expert panel review for one listing")
    parser.add_argument("listing_id")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--run-metrics", default="", help="JSON dict of run metrics")
    args = parser.parse_args()

    run_metrics: dict[str, Any] = {}
    if args.run_metrics:
        run_metrics = json.loads(args.run_metrics)

    settings = Settings()
    with build_session_factory(settings)() as session:
        lid = _resolve_listing_id(session, args.listing_id)
        verdict = review_listing(session, lid, run_metrics=run_metrics)

    if args.json:
        print(json.dumps(verdict.to_dict(), indent=2))
    else:
        print_verdict(verdict)


if __name__ == "__main__":
    main()
