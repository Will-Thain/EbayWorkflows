from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from ebay_workflows.hardening import run_data_integrity_checks
from ebay_workflows.models import (
    Base,
    CardPrice,
    ImageDetection,
    Listing,
    ListingCardCandidate,
    ListingImage,
    ListingScore,
    OcrResult,
    ScryfallCard,
)
from ebay_workflows.workflow_phase6 import run_phase6_bulk_lot_detection


def _build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_phase6_rerun_is_idempotent(tmp_path: Path) -> None:
    session = _build_session()
    card_id = uuid.uuid4()
    listing = Listing(
        external_listing_id="listing-001",
        title="MTG mixed lot",
        listing_url="https://example.com/l/1",
        currency="EUR",
        price_amount=10,
        shipping_amount=2,
        raw_payload_json={},
    )
    session.add(listing)
    session.flush()
    session.add(
        ListingImage(
            listing_id=listing.id,
            source_url="https://example.com/images/card-front-2.jpg",
            local_path="data/img1.jpg",
            download_status="succeeded",
        )
    )
    session.add(
        ScryfallCard(
            id=card_id,
            name="Sol Ring",
            set_code="lea",
            collector_number="1",
            raw_payload_json={},
        )
    )
    session.add(
        CardPrice(
            source="cardmarket",
            scryfall_id=card_id,
            currency="EUR",
            price_type="trend",
            condition="NM",
            language="en",
            price_amount=7.5,
            price_timestamp="2026-05-28T12:00:00Z",
            raw_payload_json={},
        )
    )
    session.commit()

    payload = [
        {
            "source_url": "https://example.com/images/card-front-2.jpg",
            "detected_cards": [
                {
                    "title": "Sol Ring",
                    "quantity": 2,
                    "confidence": 0.9,
                    "set_code": "lea",
                    "collector_number": "1",
                },
                {
                    "title": "Sol Ring",
                    "quantity": 1,
                    "confidence": 0.8,
                    "set_code": "lea",
                    "collector_number": "1",
                },
            ],
        }
    ]
    mock_file = tmp_path / "lots.json"
    mock_file.write_text(json.dumps(payload), encoding="utf-8")

    settings = SimpleNamespace(
        workflow_default_name="ebay_workflows",
        workflow_max_listings=None,
        workflow_max_images=None,
        workflow_singles_only=False,
        image_cache_dir="./.cache/images",
        ocr_engine="pytesseract",
        pipeline_max_image_workers=2,
        image_min_region_score=0.55,
        image_allow_full_frame_fallback=False,
        tesseract_cmd=None,
        title_match_min_score_for_pricing=0.88,
        title_match_min_score_non_mtg=0.98,
        title_match_prefilter_size=512,
        title_match_score_cutoff=55.0,
        cardmarket_max_unit_price_eur=250.0,
        ev_max_listing_cost_multiple=10.0,
        phase6_bulk_listings_only=False,
        phase6_min_lot_detections=1,
        phase6_max_lot_ev_multiple=50.0,
        phase6_use_faiss_crop_match=False,
        phase6_skip_analyzed_images=False,
        image_evidence_min_faiss_score=0.65,
        image_evidence_min_ocr_similarity=0.65,
        card_set_symbol_min_score=0.45,
        faiss_index_path="./.cache/faiss/index.bin",
        faiss_top_k=5,
        cardmarket_condition_multiplier_nm=1.0,
        cardmarket_condition_multiplier_lp=0.85,
        cardmarket_condition_multiplier_mp=0.70,
        cardmarket_condition_multiplier_hp=0.55,
        cardmarket_condition_multiplier_dmg=0.40,
        cardmarket_condition_multiplier_unspecified=0.95,
    )
    run_phase6_bulk_lot_detection(session, settings, mock_lot_file=str(mock_file))
    run_phase6_bulk_lot_detection(session, settings, mock_lot_file=str(mock_file))

    lot_detection_count = session.execute(
        select(func.count()).select_from(ImageDetection).where(ImageDetection.detection_type == "lot_card")
    ).scalar_one()
    lot_title_ocr_count = session.execute(
        select(func.count())
        .select_from(OcrResult)
        .join(ImageDetection, ImageDetection.id == OcrResult.detection_id)
        .where(ImageDetection.detection_type == "lot_card", OcrResult.field_type == "title")
    ).scalar_one()
    score = session.execute(select(ListingScore).where(ListingScore.listing_id == listing.id)).scalar_one()

    assert lot_detection_count == 2
    assert lot_title_ocr_count == 2
    assert score.scoring_version == "v2_lot"
    assert len(score.explanation_json["lot_items"]) == 2
    assert score.explanation_json["lot_items"][0]["matched_card"] == "Sol Ring"
    # Mock crops have no image path — bulk-lot pricing requires cascade image evidence (v0.3).
    assert score.explanation_json["lot_items"][0]["unit_price"] == 0


def test_integrity_check_detects_missing_candidates() -> None:
    session = _build_session()
    listing = Listing(
        external_listing_id="listing-002",
        title="MTG lot missing candidate",
        listing_url="https://example.com/l/2",
        currency="EUR",
        price_amount=5,
        shipping_amount=1,
        raw_payload_json={},
    )
    session.add(listing)
    session.flush()
    session.add(
        ListingImage(
            listing_id=listing.id,
            source_url="https://example.com/images/card-front-3.jpg",
            local_path="data/img2.jpg",
            download_status="succeeded",
        )
    )
    session.commit()

    report = run_data_integrity_checks(session)

    assert report.issues_found >= 1
    assert any("listing_card_candidates" in issue for issue in report.details)


def test_integrity_check_passes_for_consistent_minimum_graph() -> None:
    session = _build_session()
    card_id = uuid.uuid4()
    listing = Listing(
        external_listing_id="listing-003",
        title="MTG lot healthy",
        listing_url="https://example.com/l/3",
        currency="EUR",
        price_amount=20,
        shipping_amount=3,
        raw_payload_json={},
    )
    session.add(listing)
    session.flush()
    image = ListingImage(
        listing_id=listing.id,
        source_url="https://example.com/images/card-front-4.jpg",
        local_path="data/img3.jpg",
        download_status="succeeded",
    )
    session.add(image)
    session.add(
        ScryfallCard(
            id=card_id,
            name="Lightning Bolt",
            set_code="lea",
            collector_number="2",
            raw_payload_json={},
        )
    )
    session.flush()
    session.add(
        ListingCardCandidate(
            listing_id=listing.id,
            source_method="title_match",
            scryfall_id=card_id,
            match_score=0.9,
            confidence_score=0.8,
            rank_position=1,
            evidence_json={},
        )
    )
    detection = ImageDetection(
        listing_image_id=image.id,
        detection_type="lot_card",
        bbox_x=0,
        bbox_y=0,
        bbox_w=1,
        bbox_h=1,
        detection_score=0.9,
        model_version="test",
    )
    session.add(detection)
    session.flush()
    session.add(
        OcrResult(
            detection_id=detection.id,
            field_type="title",
            raw_text="Lightning Bolt",
            normalized_text="lightning bolt",
            confidence_score=0.9,
            engine_name="mock",
            engine_version="v1",
        )
    )
    session.commit()

    report = run_data_integrity_checks(session)

    assert report.checks_run == 6
    assert report.issues_found == 0
