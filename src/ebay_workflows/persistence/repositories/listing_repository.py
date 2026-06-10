"""Listing persistence queries and Phase 1 upsert helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Listing, ListingImage


@dataclass(slots=True)
class ListingUpsertOutcome:
    listing: Listing
    created: bool


class ListingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, listing_id: uuid.UUID | Any) -> Listing | None:
        return self._session.get(Listing, listing_id)

    def by_ids(self, listing_ids: set[uuid.UUID] | set[Any]) -> dict[Any, Listing]:
        if not listing_ids:
            return {}
        rows = self._session.execute(select(Listing).where(Listing.id.in_(listing_ids))).scalars().all()
        return {row.id: row for row in rows}

    def get_by_external_id(self, external_listing_id: str) -> Listing | None:
        return self._session.execute(
            select(Listing).where(Listing.external_listing_id == external_listing_id)
        ).scalar_one_or_none()

    def all(self) -> list[Listing]:
        return list(self._session.execute(select(Listing)).scalars().all())

    def upsert_from_record(
        self,
        record: Any,
        *,
        now: datetime,
    ) -> ListingUpsertOutcome:
        """Insert or update a listing from a ``ListingRecord``-like object."""
        existing = self.get_by_external_id(record.external_listing_id)
        if existing:
            existing.title = record.title
            if record.description_text is not None:
                existing.description_text = record.description_text
            existing.listing_url = record.listing_url
            existing.currency = record.currency
            existing.price_amount = record.price_amount
            existing.shipping_amount = record.shipping_amount
            existing.condition_text = record.condition_text
            existing.raw_payload_json = record.raw_payload
            existing.last_seen_at = now
            return ListingUpsertOutcome(existing, False)

        listing = Listing(
            source="ebay",
            external_listing_id=record.external_listing_id,
            title=record.title,
            description_text=record.description_text,
            listing_url=record.listing_url,
            currency=record.currency,
            price_amount=record.price_amount,
            shipping_amount=record.shipping_amount,
            condition_text=record.condition_text,
            raw_payload_json=record.raw_payload,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        self._session.add(listing)
        self._session.flush()
        return ListingUpsertOutcome(listing, True)

    def ensure_pending_image(self, listing_id: Any, source_url: str) -> ListingImage | None:
        """Add a pending image row when URL is new; return None if already present."""
        existing_img = self._session.execute(
            select(ListingImage).where(
                ListingImage.listing_id == listing_id,
                ListingImage.source_url == source_url,
            )
        ).scalar_one_or_none()
        if existing_img:
            return None
        img = ListingImage(
            listing_id=listing_id,
            source_url=source_url,
            download_status="pending",
        )
        self._session.add(img)
        return img
