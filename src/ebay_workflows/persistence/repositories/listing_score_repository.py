"""Listing score persistence queries."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ListingScore


class ListingScoreRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_listing(self, listing_id: uuid.UUID | Any) -> ListingScore | None:
        return self._session.execute(
            select(ListingScore).where(ListingScore.listing_id == listing_id)
        ).scalar_one_or_none()
