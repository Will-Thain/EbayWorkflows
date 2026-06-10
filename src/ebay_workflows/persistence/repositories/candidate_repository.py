"""Listing card candidate persistence queries."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ListingCardCandidate


class CandidateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def all(self) -> list[ListingCardCandidate]:
        return list(self._session.execute(select(ListingCardCandidate)).scalars().all())

    def for_listing(self, listing_id: uuid.UUID | Any) -> list[ListingCardCandidate]:
        return list(
            self._session.execute(
                select(ListingCardCandidate).where(ListingCardCandidate.listing_id == listing_id)
            ).scalars().all()
        )

    def all_for_scope(self, listing_ids: list | None = None) -> list[ListingCardCandidate]:
        stmt = select(ListingCardCandidate)
        if listing_ids is not None:
            stmt = stmt.where(ListingCardCandidate.listing_id.in_(listing_ids))
        return list(self._session.execute(stmt).scalars().all())

    def grouped_by_listing(self) -> dict[Any, list[ListingCardCandidate]]:
        grouped: dict[Any, list[ListingCardCandidate]] = {}
        for row in self.all():
            grouped.setdefault(row.listing_id, []).append(row)
        return grouped

    def title_match_listing_titles(self) -> dict[uuid.UUID, str]:
        """Map listing_id -> title stored on existing title_match evidence."""
        rows = self._session.execute(
            select(ListingCardCandidate.listing_id, ListingCardCandidate.evidence_json).where(
                ListingCardCandidate.source_method == "title_match"
            )
        ).all()
        matched: dict[uuid.UUID, str] = {}
        for listing_id, evidence in rows:
            if listing_id in matched:
                continue
            if isinstance(evidence, dict):
                stored_title = evidence.get("listing_title")
                if isinstance(stored_title, str):
                    matched[listing_id] = stored_title
        return matched

    def ensure_scryfall_cards_loaded(self, candidates: list[ListingCardCandidate]) -> None:
        for candidate in candidates:
            if candidate.scryfall_card is None and candidate.scryfall_id:
                self._session.refresh(candidate, attribute_names=["scryfall_card"])
