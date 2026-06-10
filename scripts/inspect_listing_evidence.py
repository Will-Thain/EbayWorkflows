"""Deep-dive evidence for sample listings after smoke run."""
from __future__ import annotations

from ebay_workflows.config import Settings
from ebay_workflows.db import build_session_factory
from ebay_workflows.models import ImageDetection, Listing, ListingCardCandidate, ListingImage, OcrResult
from sqlalchemy import func, select


def main() -> None:
    settings = Settings()
    with build_session_factory(settings)() as session:
        listing = session.execute(
            select(Listing).where(Listing.title.ilike("%Shark Typhoon%"))
        ).scalars().first()
        if not listing:
            print("no shark listing")
            return
        print("LISTING", listing.id, listing.title[:60])
        imgs = session.execute(
            select(func.count()).select_from(ListingImage).where(ListingImage.listing_id == listing.id)
        ).scalar_one()
        dets = session.execute(
            select(func.count())
            .select_from(ImageDetection)
            .join(ListingImage)
            .where(ListingImage.listing_id == listing.id, ImageDetection.detection_type == "card_region")
        ).scalar_one()
        print(f"  images={imgs} region_detections={dets}")
        cands = session.execute(
            select(ListingCardCandidate).where(ListingCardCandidate.listing_id == listing.id)
        ).scalars().all()
        for cand in cands:
            ev = cand.evidence_json or {}
            print(
                f"  rank={cand.rank_position} method={cand.source_method} score={cand.match_score} "
                f"verified={ev.get('image_verified')} pricing={ev.get('pricing_eligible')}"
            )
            print(
                f"    gate={ev.get('gate_status')} fail={ev.get('gate_fail_reason')} "
                f"bottom={(ev.get('zone_evidence') or {}).get('bottom_parsed')}"
            )

        bulk = session.execute(
            select(Listing).where(Listing.title.ilike("%Job Lot of 50%"))
        ).scalars().first()
        if bulk:
            det_count = session.execute(
                select(func.count())
                .select_from(ImageDetection)
                .join(ListingImage)
                .where(ListingImage.listing_id == bulk.id)
            ).scalar_one()
            ocr_count = session.execute(
                select(func.count())
                .select_from(OcrResult)
                .join(ImageDetection)
                .join(ListingImage)
                .where(ListingImage.listing_id == bulk.id)
            ).scalar_one()
            print(f"BULK {bulk.title[:50]} detections={det_count} ocr_rows={ocr_count}")


if __name__ == "__main__":
    main()
