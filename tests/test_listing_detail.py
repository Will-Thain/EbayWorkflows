from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ebay_workflows.gui.listing_detail import (
    DetectionDetail,
    MatchDetail,
    detection_for_match,
    fetch_listing_detail,
)
from ebay_workflows.models import (
    Base,
    ImageDetection,
    Listing,
    ListingCardCandidate,
    ListingImage,
    OcrResult,
    ScryfallCard,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_fetch_listing_detail_orders_matches_and_images(tmp_path) -> None:
    session = _session()
    cache = tmp_path / "cache"
    cache.mkdir()
    img_path = cache / "listing.jpg"
    img_path.write_bytes(b"fake")

    listing_id = uuid.uuid4()
    card_a = uuid.uuid4()
    card_b = uuid.uuid4()
    session.add(
        Listing(
            id=listing_id,
            external_listing_id="ebay-1",
            title="Lot of cards",
            listing_url="https://ebay.example/item/1",
            currency="GBP",
            price_amount=10.0,
        )
    )
    session.add_all(
        [
            ScryfallCard(id=card_a, name="Lightning Bolt", set_code="lea", raw_payload_json={}),
            ScryfallCard(id=card_b, name="Counterspell", set_code="m10", raw_payload_json={}),
        ]
    )
    image_id = uuid.uuid4()
    session.add(
        ListingImage(
            id=image_id,
            listing_id=listing_id,
            source_url="https://img.example/1.jpg",
            local_path=str(img_path),
            download_status="succeeded",
        )
    )
    detection_id = uuid.uuid4()
    session.add(
        ImageDetection(
            id=detection_id,
            listing_image_id=image_id,
            bbox_x=0.1,
            bbox_y=0.2,
            bbox_w=0.3,
            bbox_h=0.4,
            detection_score=0.9,
        )
    )
    session.add(
        OcrResult(
            detection_id=detection_id,
            field_type="title",
            raw_text="Lightning Bolt",
            confidence_score=0.95,
        )
    )
    session.add_all(
        [
            ListingCardCandidate(
                listing_id=listing_id,
                scryfall_id=card_b,
                match_score=0.7,
                confidence_score=0.6,
                rank_position=2,
                evidence_json={
                "image_verified": True,
                "cardmarket_price": {"currency": "EUR", "price_amount": 2.5, "price_type": "trend"},
            },
            ),
            ListingCardCandidate(
                listing_id=listing_id,
                scryfall_id=card_a,
                match_score=0.95,
                confidence_score=0.9,
                rank_position=1,
                evidence_json={
                "image_verified": True,
                "ocr_verification": {"similarity": 0.95, "ocr_title": "Lightning Bolt"},
                "cardmarket_price": {"currency": "EUR", "price_amount": 5.0, "price_type": "trend"},
            },
            ),
        ]
    )
    session.commit()

    detail = fetch_listing_detail(session, listing_id, image_cache_dir=str(cache))
    assert detail is not None
    assert len(detail.images) == 1
    assert detail.images[0].local_path == str(img_path)
    assert len(detail.matches) == 2
    assert detail.matches[0].rank_position == 1
    assert detail.matches[0].card_name == "Lightning Bolt"
    assert detail.matches[0].price_amount == 5.0
    assert detail.matches[1].card_name == "Counterspell"


def test_detection_for_match_prefers_ocr_title() -> None:
    detections = [
        DetectionDetail("1", 0, 0, 1, 1, 0.5, ocr_title="Lightning Bolt"),
        DetectionDetail("2", 0.5, 0.5, 0.2, 0.2, 0.8, ocr_title="Other Card"),
    ]
    match = MatchDetail(
        rank_position=1,
        scryfall_id="x",
        card_name="Lightning Bolt",
        set_code="lea",
        match_score=0.95,
        confidence_score=0.9,
        price_amount=5.0,
        price_currency="EUR",
        price_type="trend",
    )
    assert detection_for_match(detections, match) == 0
