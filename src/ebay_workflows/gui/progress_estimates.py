from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Listing, ListingImage, ListingScore


def estimate_job_total(session: Session, job_id: str, params: dict[str, Any]) -> tuple[int, str] | None:
    """Best-effort total item count before or during a job (for progress bar range)."""
    if job_id == "phase1":
        max_pages = int(params.get("max_pages", 1))
        page_size = int(params.get("page_size", 50))
        return max(1, max_pages * page_size), "listings"
    if job_id == "phase2":
        total = session.scalar(select(func.count()).select_from(Listing))
        return (int(total), "listings") if total else None
    if job_id == "phase4":
        total = session.scalar(select(func.count()).select_from(Listing))
        return (int(total), "listings") if total else None
    if job_id == "phase5":
        total = session.scalar(
            select(func.count())
            .select_from(ListingImage)
            .where(ListingImage.local_path.is_not(None), ListingImage.download_status == "succeeded")
        )
        return (int(total), "images") if total else None
    if job_id == "phase6":
        total = session.scalar(
            select(func.count())
            .select_from(ListingImage)
            .where(ListingImage.local_path.is_not(None), ListingImage.download_status == "succeeded")
        )
        return (int(total), "images") if total else None
    return None


def poll_job_progress(session: Session, job_id: str) -> tuple[int, int, str] | None:
    """Infer current/total from DB while a job is running (fallback when logs are quiet)."""
    if job_id == "phase4":
        total = session.scalar(select(func.count()).select_from(Listing)) or 0
        current = session.scalar(select(func.count()).select_from(ListingScore)) or 0
        if total > 0:
            return int(current), int(total), "listings"
    return None
