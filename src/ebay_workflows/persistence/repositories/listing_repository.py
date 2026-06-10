"""Listing persistence queries."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Listing


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
