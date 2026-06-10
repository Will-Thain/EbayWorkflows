"""Tests for workflow sample limits."""
from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ebay_workflows.config import Settings
from ebay_workflows.models import Base, Listing, ListingImage
from ebay_workflows.operations.workflow_sample import (
    fetch_limited_listing_images,
    fetch_limited_listings,
    limited_listing_ids,
    sample_scope_label,
    with_sample_overrides,
    discover_single_listings_with_images,
)


def _settings(**overrides: object) -> Settings:
    base = {
        "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
        "SCRYFALL_BULK_URI": "https://example.com/bulk",
        "CARDMARKET_BULK_FILE_PATH": "./data/cardmarket/prices.csv",
        "IMAGE_CACHE_DIR": "./.cache/images",
        "FAISS_INDEX_PATH": "./.cache/faiss/index.bin",
        "GLOBAL_REQUESTS_PER_MINUTE_CAP": 90,
    }
    base.update(overrides)
    return Settings(**base)


def _build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_with_sample_overrides_leaves_unset_fields() -> None:
    base = _settings()
    updated = with_sample_overrides(base, max_listings=5)
    assert updated.workflow_max_listings == 5
    assert updated.workflow_max_images is None


def test_fetch_limited_listings_and_images() -> None:
    settings = _settings(WORKFLOW_MAX_LISTINGS=2, WORKFLOW_MAX_IMAGES=10)
    session = _build_session()
    try:
        for idx in range(4):
            listing_id = uuid.UUID(int=idx)
            listing = Listing(
                id=listing_id,
                external_listing_id=f"item-{idx}",
                title=f"Listing {idx}",
                listing_url=f"https://example.com/{idx}",
                currency="EUR",
                price_amount=1,
                raw_payload_json={},
            )
            session.add(listing)
            session.flush()
            session.add(
                ListingImage(
                    listing_id=listing.id,
                    source_url=f"https://example.com/{idx}.jpg",
                    download_status="succeeded",
                )
            )
        session.commit()

        listings = fetch_limited_listings(session, settings)
        assert len(listings) == 2
        assert [listing.external_listing_id for listing in listings] == ["item-0", "item-1"]

        images = fetch_limited_listing_images(session, settings)
        assert len(images) == 2
    finally:
        session.close()


def test_sample_scope_label() -> None:
    settings = _settings(WORKFLOW_MAX_LISTINGS=10, WORKFLOW_MAX_IMAGES=30, WORKFLOW_SINGLES_ONLY=True)
    assert sample_scope_label(settings) == "singles-only, listings<=10, images<=30"


def test_limited_listing_ids_singles_only() -> None:
    settings = _settings(WORKFLOW_MAX_LISTINGS=2, WORKFLOW_SINGLES_ONLY=True)
    session = _build_session()
    try:
        for idx, title in enumerate(["MTG Lot of 50 cards", "Lightning Bolt NM", "Sol Ring LP"]):
            listing = Listing(
                id=uuid.UUID(int=idx + 1),
                external_listing_id=f"item-{idx}",
                title=title,
                listing_url=f"https://example.com/{idx}",
                currency="EUR",
                price_amount=1,
                raw_payload_json={},
            )
            session.add(listing)
            session.flush()
            session.add(
                ListingImage(
                    listing_id=listing.id,
                    source_url=f"https://example.com/{idx}.jpg",
                    local_path=f"./img-{idx}.jpg",
                    download_status="succeeded",
                )
            )
        session.commit()
        ids = limited_listing_ids(session, settings)
        assert len(ids) == 2
    finally:
        session.close()


def test_discover_single_listings_excludes_used_ids() -> None:
    session = _build_session()
    try:
        ids = [uuid.UUID(int=idx + 1) for idx in range(3)]
        for idx, title in enumerate(["Lightning Bolt NM", "Sol Ring LP", "Counterspell MP"]):
            listing = Listing(
                id=ids[idx],
                external_listing_id=f"item-{idx}",
                title=title,
                listing_url=f"https://example.com/{idx}",
                currency="EUR",
                price_amount=1,
                raw_payload_json={},
            )
            session.add(listing)
            session.flush()
            session.add(
                ListingImage(
                    listing_id=listing.id,
                    source_url=f"https://example.com/{idx}.jpg",
                    local_path=f"./img-{idx}.jpg",
                    download_status="succeeded",
                )
            )
        session.commit()

        all_three = discover_single_listings_with_images(session, limit=10)
        assert len(all_three) == 3

        skip_first = discover_single_listings_with_images(
            session,
            limit=10,
            exclude_listing_ids={ids[0]},
        )
        assert len(skip_first) == 2
        assert skip_first[0].id == ids[1]
    finally:
        session.close()


def test_fetch_limited_images_only() -> None:
    settings = _settings(WORKFLOW_MAX_IMAGES=3)
    session = _build_session()
    try:
        listing = Listing(
            id=uuid.UUID(int=99),
            external_listing_id="item-bulk",
            title="Bulk lot",
            listing_url="https://example.com/bulk",
            currency="EUR",
            price_amount=1,
            raw_payload_json={},
        )
        session.add(listing)
        session.flush()
        for idx in range(5):
            session.add(
                ListingImage(
                    listing_id=listing.id,
                    source_url=f"https://example.com/bulk-{idx}.jpg",
                    download_status="succeeded",
                )
            )
        session.commit()

        images = fetch_limited_listing_images(session, settings)
        assert len(images) == 3
    finally:
        session.close()
