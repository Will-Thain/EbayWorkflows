from __future__ import annotations

import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ebay_workflows.models import (
    Base,
    ImageDetection,
    Listing,
    ListingCardCandidate,
    ListingImage,
    ListingScore,
    OcrResult,
    ScryfallCard,
)
from ebay_workflows.operations.clear_matching_data import clear_matching_artifacts, count_matching_artifacts


def _build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_clear_matching_artifacts_preserves_listings_and_images() -> None:
    session = _build_session()
    session.add(ScryfallCard(id=uuid.uuid4(), name="Sol Ring", raw_payload_json={}))
    session.flush()
    listing = Listing(
        external_listing_id="l-1",
        title="MTG Sol Ring LP",
        listing_url="https://example.com/1",
        currency="EUR",
        price_amount=5,
        shipping_amount=1,
        raw_payload_json={},
    )
    session.add(listing)
    session.flush()
    image = ListingImage(
        listing_id=listing.id,
        source_url="https://example.com/img.jpg",
        local_path="./img.jpg",
        download_status="succeeded",
    )
    session.add(image)
    session.flush()
    detection = ImageDetection(listing_image_id=image.id, detection_type="card_region")
    session.add(detection)
    session.flush()
    session.add(
        OcrResult(
            detection_id=detection.id,
            field_type="title",
            raw_text="Sol Ring",
            normalized_text="sol ring",
            confidence_score=0.8,
            engine_name="test",
        )
    )
    session.add(
        ListingCardCandidate(
            listing_id=listing.id,
            source_method="title_match",
            match_score=0.9,
            confidence_score=0.9,
            rank_position=1,
            evidence_json={},
        )
    )
    session.add(
        ListingScore(
            listing_id=listing.id,
            ev_raw=1,
            ev_adjusted=1,
            confidence_score=0.9,
            risk_score=0.1,
            rank_value=1,
            scoring_version="v2_hybrid",
            explanation_json={},
        )
    )
    session.commit()

    before = count_matching_artifacts(session)
    assert before["listing_card_candidates"] == 1
    assert before["listing_scores"] == 1

    report = clear_matching_artifacts(session, export_dir=None)
    assert report.listing_candidates_deleted == 1
    assert report.listing_scores_deleted == 1
    assert report.image_detections_deleted == 1
    assert report.ocr_results_deleted == 1

    after = count_matching_artifacts(session)
    assert after["listing_card_candidates"] == 0
    assert after["listing_scores"] == 0
    assert session.execute(select(Listing)).scalar_one().title == "MTG Sol Ring LP"
    assert session.execute(select(ListingImage)).scalar_one().local_path == "./img.jpg"
