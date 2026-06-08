from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ListingFavorite


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_favorited(session: Session, listing_id: uuid.UUID) -> bool:
    return (
        session.execute(
            select(ListingFavorite.listing_id).where(ListingFavorite.listing_id == listing_id)
        ).scalar_one_or_none()
        is not None
    )


def set_favorite(session: Session, listing_id: uuid.UUID, *, note: str | None = None) -> None:
    row = session.get(ListingFavorite, listing_id)
    if row:
        if note is not None:
            row.note = note.strip() or None
        row.favorited_at = _now()
    else:
        session.add(
            ListingFavorite(
                listing_id=listing_id,
                note=note.strip() if note else None,
                favorited_at=_now(),
            )
        )
    session.commit()


def clear_favorite(session: Session, listing_id: uuid.UUID) -> None:
    row = session.get(ListingFavorite, listing_id)
    if row:
        session.delete(row)
        session.commit()


def get_note(session: Session, listing_id: uuid.UUID) -> str | None:
    row = session.get(ListingFavorite, listing_id)
    return row.note if row else None
