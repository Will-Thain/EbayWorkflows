"""Run Phase 5 analysis on a single listing (operator validation)."""
from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from sqlalchemy import select, cast, String

from ebay_workflows.config import Settings
from ebay_workflows.db import build_session_factory
from ebay_workflows.models import ImageDetection, Listing, ListingCardCandidate, ListingImage, OcrResult
from ebay_workflows.recognition.embedding_index import index_exists, propose_embedding_candidates, apply_embedding_evidence
from ebay_workflows.recognition.phase5_analysis import analyze_listing_image
from ebay_workflows.recognition.cascade_persist import cascade_regions_from_analysis
from ebay_workflows.candidates.candidate_sync import apply_cascade_proposals_to_candidates
from ebay_workflows.candidates.image_evidence import apply_per_listing_verification_gates
from ebay_workflows.workflows.phase5 import (
    RegionPersistResult,
    _apply_region_evidence_to_candidates,
    _clear_card_regions,
)


def _persist_region_detection(
    session,
    listing_image: ListingImage,
    region,
    fields: dict,
    *,
    model_version: str,
    engine_name: str,
    engine_version: str,
) -> RegionPersistResult:
    detection = ImageDetection(
        listing_image_id=listing_image.id,
        detection_type="card_region",
        bbox_x=region.bbox_x,
        bbox_y=region.bbox_y,
        bbox_w=region.bbox_w,
        bbox_h=region.bbox_h,
        detection_score=region.score,
        model_version=model_version,
    )
    session.add(detection)
    session.flush()
    region_path = region.crop_path or listing_image.local_path or ""
    best_title: str | None = None
    for field_type, (raw_text, confidence) in fields.items():
        session.add(
            OcrResult(
                detection_id=detection.id,
                field_type=field_type,
                raw_text=raw_text,
                normalized_text=raw_text.lower(),
                confidence_score=confidence,
                engine_name=engine_name,
                engine_version=engine_version,
                region_image_path=region_path,
            )
        )
        if field_type == "title":
            best_title = raw_text
    return RegionPersistResult(best_title, detection.id, region_path)


def _persist_region_shell(
    session,
    listing_image: ListingImage,
    region,
    *,
    model_version: str,
) -> RegionPersistResult:
    detection = ImageDetection(
        listing_image_id=listing_image.id,
        detection_type="card_region",
        bbox_x=region.bbox_x,
        bbox_y=region.bbox_y,
        bbox_w=region.bbox_w,
        bbox_h=region.bbox_h,
        detection_score=region.score,
        model_version=model_version,
    )
    session.add(detection)
    session.flush()
    region_path = region.crop_path or listing_image.local_path or ""
    return RegionPersistResult(None, detection.id, region_path)


def _resolve_listing(session, listing_id: str) -> Listing:
    try:
        lid = uuid.UUID(listing_id)
        listing = session.get(Listing, lid)
        if listing is not None:
            return listing
    except ValueError:
        pass
    row = session.execute(
        select(Listing).where(cast(Listing.id, String).like(f"{listing_id}%"))
    ).scalars().first()
    if row is None:
        raise SystemExit(f"Listing not found: {listing_id}")
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Phase 5 on one listing")
    parser.add_argument("listing_id", help="Listing UUID or prefix")
    parser.add_argument("--max-images", type=int, default=2, help="Max images to analyze")
    parser.add_argument("--use-embedding", action="store_true", default=True)
    parser.add_argument("--no-embedding", dest="use_embedding", action="store_false")
    args = parser.parse_args()

    settings = Settings()
    settings.torch_device = "cpu"
    crop_dir = str(Path(settings.image_cache_dir) / "crops" / "phase5_validate")
    Path(crop_dir).mkdir(parents=True, exist_ok=True)
    embedding_enabled = args.use_embedding and index_exists(settings.faiss_index_path)

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        listing = _resolve_listing(session, args.listing_id)
        print(f"Listing: {listing.id}")
        print(f"Title:   {listing.title}")

        images = list(
            session.execute(
                select(ListingImage)
                .where(
                    ListingImage.listing_id == listing.id,
                    ListingImage.local_path.is_not(None),
                )
                .limit(args.max_images)
            ).scalars().all()
        )
        if not images:
            raise SystemExit("No cached images for listing")

        candidates = list(
            session.execute(
                select(ListingCardCandidate).where(ListingCardCandidate.listing_id == listing.id)
            ).scalars().all()
        )
        for row in candidates:
            if row.scryfall_card is None and row.scryfall_id:
                session.refresh(row, attribute_names=["scryfall_card"])

        scryfall_cards = []
        seen: set[str] = set()
        for row in candidates:
            card = row.scryfall_card
            if card is None:
                continue
            cid = str(card.id)
            if cid in seen:
                continue
            seen.add(cid)
            scryfall_cards.append(card)

        total_regions = 0
        total_detections = 0
        embedding_updates = 0
        candidates_updated = 0

        for img in images:
            local_path = img.local_path or ""
            if not Path(local_path).is_file():
                print(f"SKIP missing file: {local_path}")
                continue

            _clear_card_regions(session, img.id)
            print(f"\nImage {img.id}: {local_path}")

            analysis = analyze_listing_image(
                listing_image_id=str(img.id),
                listing_id=str(listing.id),
                local_path=local_path,
                crop_dir=crop_dir,
                settings=settings,
                use_embedding=embedding_enabled,
                scryfall_cards=scryfall_cards,
                listing_title=listing.title,
            )

            if analysis.skipped:
                print("  SKIPPED (no visible cards / tier0)")
                continue

            region_views = cascade_regions_from_analysis(analysis)
            print(f"  regions={len(region_views)} cascade={analysis.cascade is not None}")

            detection_id_by_region: dict[str, str] = {}
            region_path_by_region: dict[str, str] = {}

            for region_view in region_views:
                region = region_view.region
                fields = region_view.fields
                zone_evidence = region_view.zone_evidence
                total_regions += 1

                if fields:
                    persist = _persist_region_detection(
                        session,
                        img,
                        region,
                        fields,
                        model_version="phase5_validate_v03",
                        engine_name=settings.ocr_engine,
                        engine_version="v3",
                    )
                elif zone_evidence:
                    persist = _persist_region_shell(
                        session,
                        img,
                        region,
                        model_version="phase5_validate_v03",
                    )
                else:
                    persist = None

                if persist is None:
                    continue

                total_detections += 1
                region_key = region_view.region_id or str(persist.detection_id)
                detection_id_by_region[region_key] = str(persist.detection_id)
                region_path_by_region[region_key] = persist.region_path
                print(
                    f"  region score={getattr(region, 'score', '?')} "
                    f"bottom={((zone_evidence or {}).get('bottom_parsed') or {}).get('set_code')}"
                )

                candidates_updated += _apply_region_evidence_to_candidates(
                    candidates,
                    listing_image_id=str(img.id),
                    detection_id=str(persist.detection_id),
                    region_path=persist.region_path,
                    ocr_title=persist.best_title,
                    fields=fields,
                    zone_evidence=zone_evidence,
                    settings=settings,
                )

                if region_view.embedding_matches:
                    embedding_updates += propose_embedding_candidates(
                        session,
                        listing.id,
                        candidates,
                        region_view.embedding_matches,
                        settings,
                    )
                    embedding_updates += apply_embedding_evidence(
                        candidates,
                        region_view.embedding_matches,
                        listing_id=listing.id,
                        settings=settings,
                    )

            if analysis.cascade is not None:
                candidates_updated += apply_cascade_proposals_to_candidates(
                    candidates,
                    analysis.cascade,
                    listing_image_id=str(img.id),
                    detection_id_by_region=detection_id_by_region,
                    region_path_by_region=region_path_by_region,
                )

        verified, gated = apply_per_listing_verification_gates(candidates, settings)
        session.commit()

        print("\n--- Summary ---")
        print(f"images_analyzed={len(images)}")
        print(f"regions={total_regions} detections_persisted={total_detections}")
        print(f"candidates_updated={candidates_updated} embedding_updates={embedding_updates}")
        print(f"verified={verified} gated={gated}")
        print(f"embedding_enabled={embedding_enabled}")


if __name__ == "__main__":
    main()
