"""Investigate sample-scope pipeline: expected vs actual DB state."""
from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import func, select, text

from ebay_workflows.config import Settings
from ebay_workflows.db import build_session_factory
from ebay_workflows.models import (
    ImageDetection,
    Listing,
    ListingCardCandidate,
    ListingImage,
    ListingScore,
    OcrResult,
)
from ebay_workflows.operations.listing_filters import is_bulk_lot_title


def sample_listing_ids(session, max_listings: int) -> list:
    return list(
        session.execute(select(Listing.id).order_by(Listing.id).limit(max_listings)).scalars().all()
    )


def _verified_candidates(session, listing_ids: list) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            ListingCardCandidate.listing_id,
            ListingCardCandidate.scryfall_id,
            ListingCardCandidate.source_method,
            ListingCardCandidate.evidence_json,
        ).where(ListingCardCandidate.listing_id.in_(listing_ids))
    ).all()
    out: list[dict[str, Any]] = []
    for listing_id, scryfall_id, source_method, evidence in rows:
        ev = evidence or {}
        if ev.get("image_verified"):
            out.append(
                {
                    "listing_id": str(listing_id),
                    "scryfall_id": str(scryfall_id) if scryfall_id else None,
                    "source_method": source_method,
                    "verification_source": ev.get("image_verification_source"),
                }
            )
    return out


def investigate(session, max_listings: int, label: str) -> dict[str, Any]:
    ids = sample_listing_ids(session, max_listings)
    if not ids:
        return {"label": label, "error": "no listings in DB"}

    listings = session.execute(select(Listing).where(Listing.id.in_(ids))).scalars().all()
    bulk = sum(1 for listing in listings if is_bulk_lot_title(listing.title))
    singles = len(listings) - bulk

    images = session.execute(
        select(func.count())
        .select_from(ListingImage)
        .where(ListingImage.listing_id.in_(ids))
    ).scalar_one()
    images_ok = session.execute(
        select(func.count())
        .select_from(ListingImage)
        .where(ListingImage.listing_id.in_(ids), ListingImage.local_path.isnot(None))
    ).scalar_one()

    candidates = session.execute(
        select(func.count())
        .select_from(ListingCardCandidate)
        .where(ListingCardCandidate.listing_id.in_(ids))
    ).scalar_one()
    title_candidates = session.execute(
        select(func.count())
        .select_from(ListingCardCandidate)
        .where(
            ListingCardCandidate.listing_id.in_(ids),
            ListingCardCandidate.source_method == "title_match",
        )
    ).scalar_one()

    detections = session.execute(
        select(func.count())
        .select_from(ImageDetection)
        .join(ListingImage, ImageDetection.listing_image_id == ListingImage.id)
        .where(ListingImage.listing_id.in_(ids))
    ).scalar_one()
    region_detections = session.execute(
        select(func.count())
        .select_from(ImageDetection)
        .join(ListingImage, ImageDetection.listing_image_id == ListingImage.id)
        .where(
            ListingImage.listing_id.in_(ids),
            ImageDetection.detection_type == "card_region",
        )
    ).scalar_one()

    ocr_rows = session.execute(
        select(func.count())
        .select_from(OcrResult)
        .join(ImageDetection, OcrResult.detection_id == ImageDetection.id)
        .join(ListingImage, ImageDetection.listing_image_id == ListingImage.id)
        .where(ListingImage.listing_id.in_(ids))
    ).scalar_one()

    verified = _verified_candidates(session, ids)
    pricing_eligible = session.execute(
        select(func.count())
        .select_from(ListingCardCandidate)
        .where(
            ListingCardCandidate.listing_id.in_(ids),
            ListingCardCandidate.evidence_json["pricing_eligible"].as_boolean().is_(True),
        )
    ).scalar_one()

    scores = session.execute(
        select(func.count())
        .select_from(ListingScore)
        .where(ListingScore.listing_id.in_(ids))
    ).scalar_one()
    positive_rank = session.execute(
        select(func.count())
        .select_from(ListingScore)
        .where(ListingScore.listing_id.in_(ids), ListingScore.rank_value > 0)
    ).scalar_one()

    gate_status_rows = session.execute(
        text(
            """
            SELECT COALESCE(c.evidence_json->>'gate_status',
                            c.evidence_json->'ocr_verification'->>'gate_status',
                            'none') AS gate_status,
                   COUNT(*) AS n
            FROM listing_card_candidates c
            WHERE c.listing_id = ANY(CAST(:ids AS uuid[]))
            GROUP BY 1
            ORDER BY n DESC
            LIMIT 10
            """
        ),
        {"ids": ids},
    ).all()

    bottom_parsed = session.execute(
        text(
            """
            SELECT COUNT(*) FROM listing_card_candidates c
            WHERE c.listing_id = ANY(CAST(:ids AS uuid[]))
              AND (
                (c.evidence_json->'zone_evidence'->'bottom_parsed'->>'set_code') IS NOT NULL
                OR (c.evidence_json->'ocr_verification'->'bottom_parsed'->>'set_code') IS NOT NULL
              )
            """
        ),
        {"ids": ids},
    ).scalar_one()

    return {
        "label": label,
        "sample_listings": len(ids),
        "bulk_lot_titles": bulk,
        "single_card_titles": singles,
        "images_total": int(images),
        "images_with_local_path": int(images_ok),
        "candidates_total": int(candidates),
        "title_match_candidates": int(title_candidates),
        "detections_total": int(detections),
        "region_detections": int(region_detections),
        "ocr_rows": int(ocr_rows),
        "verified_candidates": len(verified),
        "verified_details": verified[:5],
        "pricing_eligible_candidates": int(pricing_eligible),
        "scored_listings": int(scores),
        "listings_rank_value_gt_0": int(positive_rank),
        "candidates_with_bottom_parsed": int(bottom_parsed),
        "gate_status_counts": {row[0]: int(row[1]) for row in gate_status_rows},
        "sample_titles": [listing.title[:70] for listing in sorted(listings, key=lambda x: str(x.id))[:5]],
    }


def print_report(report: dict[str, Any]) -> None:
    print(f"\n=== Investigation: {report.get('label', '?')} ===")
    if "error" in report:
        print(f"ERROR: {report['error']}")
        return
    for key in (
        "sample_listings",
        "bulk_lot_titles",
        "single_card_titles",
        "images_total",
        "images_with_local_path",
        "candidates_total",
        "title_match_candidates",
        "detections_total",
        "region_detections",
        "ocr_rows",
        "verified_candidates",
        "pricing_eligible_candidates",
        "scored_listings",
        "listings_rank_value_gt_0",
        "candidates_with_bottom_parsed",
    ):
        print(f"  {key}: {report.get(key)}")
    print(f"  gate_status_counts: {report.get('gate_status_counts')}")
    if report.get("verified_details"):
        print(f"  verified_details (first 5): {json.dumps(report['verified_details'], indent=2)}")
    print(f"  sample_titles: {report.get('sample_titles')}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-listings", type=int, default=20)
    parser.add_argument("--label", default="snapshot")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    settings = Settings()
    factory = build_session_factory(settings)
    with factory() as session:
        report = investigate(session, args.max_listings, args.label)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
