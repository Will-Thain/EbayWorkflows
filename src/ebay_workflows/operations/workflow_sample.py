"""Limit workflow phases to a small listing/image sample for smoke testing."""
from __future__ import annotations

import uuid

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Listing, ListingImage
from ..operations.listing_filters import is_probable_single_card_listing


def _listing_has_cached_image(session: Session, listing_id: uuid.UUID) -> bool:
    return bool(
        session.execute(
            select(
                exists().where(
                    ListingImage.listing_id == listing_id,
                    ListingImage.local_path.is_not(None),
                )
            )
        ).scalar_one()
    )


def limited_listing_ids(session: Session, settings: Settings) -> list | None:
    """Return listing ids in stable order when WORKFLOW_MAX_LISTINGS is set."""
    cap = settings.workflow_max_listings
    if cap is None or cap <= 0:
        return None

    if settings.workflow_singles_only:
        ids: list[uuid.UUID] = []
        rows = session.execute(select(Listing.id, Listing.title).order_by(Listing.id)).all()
        for listing_id, title in rows:
            if not is_probable_single_card_listing(title):
                continue
            if not _listing_has_cached_image(session, listing_id):
                continue
            ids.append(listing_id)
            if len(ids) >= cap:
                break
        return ids

    return list(
        session.execute(select(Listing.id).order_by(Listing.id).limit(cap)).scalars().all()
    )


def fetch_limited_listings(session: Session, settings: Settings) -> list[Listing]:
    ids = limited_listing_ids(session, settings)
    stmt = select(Listing).order_by(Listing.id)
    if ids is not None:
        stmt = stmt.where(Listing.id.in_(ids))
    return list(session.execute(stmt).scalars().all())


def with_sample_overrides(
    settings: Settings,
    *,
    max_listings: int | None = None,
    max_images: int | None = None,
    singles_only: bool | None = None,
) -> Settings:
    updates: dict[str, int | bool | None] = {}
    if max_listings is not None:
        updates["workflow_max_listings"] = max_listings
    if max_images is not None:
        updates["workflow_max_images"] = max_images
    if singles_only is not None:
        updates["workflow_singles_only"] = singles_only
    if not updates:
        return settings
    return settings.model_copy(update=updates)


def sample_scope_label(settings: Settings) -> str | None:
    parts: list[str] = []
    if settings.workflow_singles_only:
        parts.append("singles-only")
    if settings.workflow_max_listings:
        parts.append(f"listings<={settings.workflow_max_listings}")
    if settings.workflow_max_images:
        parts.append(f"images<={settings.workflow_max_images}")
    return ", ".join(parts) if parts else None


def fetch_limited_listing_images(session: Session, settings: Settings) -> list[ListingImage]:
    ids = limited_listing_ids(session, settings)
    stmt = select(ListingImage).order_by(ListingImage.id)
    if ids is not None:
        stmt = stmt.where(ListingImage.listing_id.in_(ids))
    cap = settings.workflow_max_images
    if cap is not None and cap > 0:
        stmt = stmt.limit(cap)
    return list(session.execute(stmt).scalars().all())


def discover_single_listings_with_images(
    session: Session,
    *,
    limit: int,
    offset: int = 0,
    exclude_listing_ids: set[uuid.UUID] | None = None,
) -> list[Listing]:
    """Stable-ordered singles that have at least one cached image."""
    excluded = exclude_listing_ids or set()
    picked: list[Listing] = []
    rows = session.execute(select(Listing).order_by(Listing.id)).scalars().all()
    skipped = 0
    for listing in rows:
        if listing.id in excluded:
            continue
        if not is_probable_single_card_listing(listing.title):
            continue
        if not _listing_has_cached_image(session, listing.id):
            continue
        if skipped < offset:
            skipped += 1
            continue
        picked.append(listing)
        if len(picked) >= limit:
            break
    return picked


def count_eligible_single_listings_with_images(
    session: Session,
    *,
    exclude_listing_ids: set[uuid.UUID] | None = None,
) -> int:
    """Count singles with cached images, optionally excluding already-used ids."""
    excluded = exclude_listing_ids or set()
    count = 0
    rows = session.execute(select(Listing.id, Listing.title)).all()
    for listing_id, title in rows:
        if listing_id in excluded:
            continue
        if not is_probable_single_card_listing(title):
            continue
        if not _listing_has_cached_image(session, listing_id):
            continue
        count += 1
    return count
