from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    CardPrice,
    Listing,
    ListingCardCandidate,
    ListingFavorite,
    ListingImage,
    ListingScore,
    ScryfallCard,
    WorkflowRun,
    WorkflowStep,
)

QueryRunner = Callable[[Session], tuple[list[str], list[tuple[Any, ...]]]]


@dataclass(frozen=True, slots=True)
class CuratedQuery:
    query_id: str
    label: str
    run: QueryRunner


def _table_counts(session: Session) -> tuple[list[str], list[tuple[Any, ...]]]:
    headers = ["table", "row_count"]
    tables = [
        ("listings", Listing),
        ("listing_images", ListingImage),
        ("listing_card_candidates", ListingCardCandidate),
        ("listing_scores", ListingScore),
        ("listing_favorites", ListingFavorite),
        ("scryfall_cards", ScryfallCard),
        ("card_prices", CardPrice),
        ("workflow_runs", WorkflowRun),
        ("workflow_steps", WorkflowStep),
    ]
    rows = [
        (name, session.scalar(select(func.count()).select_from(model)))
        for name, model in tables
    ]
    return headers, rows


def _recent_workflow_runs(session: Session) -> tuple[list[str], list[tuple[Any, ...]]]:
    runs = session.execute(
        select(WorkflowRun).order_by(WorkflowRun.started_at.desc()).limit(20)
    ).scalars().all()
    headers = ["id", "workflow_name", "status", "started_at", "finished_at"]
    rows = [
        (str(r.id), r.workflow_name, r.status, r.started_at, r.finished_at)
        for r in runs
    ]
    return headers, rows


def _recent_workflow_steps(session: Session) -> tuple[list[str], list[tuple[Any, ...]]]:
    steps = session.execute(
        select(WorkflowStep).order_by(WorkflowStep.started_at.desc()).limit(50)
    ).scalars().all()
    headers = ["step_name", "phase", "status", "started_at", "finished_at", "run_id"]
    rows = [
        (
            s.step_name,
            s.phase_number,
            s.status,
            s.started_at,
            s.finished_at,
            str(s.run_id),
        )
        for s in steps
    ]
    return headers, rows


def _failed_images(session: Session) -> tuple[list[str], list[tuple[Any, ...]]]:
    images = session.execute(
        select(ListingImage, Listing.title)
        .join(Listing, Listing.id == ListingImage.listing_id)
        .where(ListingImage.download_status == "failed")
        .limit(100)
    ).all()
    headers = ["listing_title", "source_url", "error"]
    rows = []
    for img, title in images:
        err = ""
        if img.error_json and isinstance(img.error_json, dict):
            err = str(img.error_json.get("message", ""))[:120]
        rows.append((title[:80], img.source_url[:80], err))
    return headers, rows


def _listings_without_scores(session: Session) -> tuple[list[str], list[tuple[Any, ...]]]:
    listings = session.execute(
        select(Listing)
        .outerjoin(ListingScore, ListingScore.listing_id == Listing.id)
        .where(ListingScore.id.is_(None))
        .limit(100)
    ).scalars().all()
    headers = ["listing_id", "title", "price", "currency"]
    rows = [
        (str(lst.id), lst.title[:80], float(lst.price_amount), lst.currency)
        for lst in listings
    ]
    return headers, rows


def _top_rank_value(session: Session) -> tuple[list[str], list[tuple[Any, ...]]]:
    rows_db = session.execute(
        select(Listing, ListingScore)
        .join(ListingScore, ListingScore.listing_id == Listing.id)
        .order_by(ListingScore.rank_value.desc())
        .limit(50)
    ).all()
    headers = ["rank_value", "ev_adjusted", "title", "listing_id"]
    result = [
        (
            float(score.rank_value),
            float(score.ev_adjusted),
            listing.title[:80],
            str(listing.id),
        )
        for listing, score in rows_db
    ]
    return headers, result


def _favourites(session: Session) -> tuple[list[str], list[tuple[Any, ...]]]:
    rows_db = session.execute(
        select(Listing, ListingFavorite, ListingScore)
        .join(ListingFavorite, ListingFavorite.listing_id == Listing.id)
        .outerjoin(ListingScore, ListingScore.listing_id == Listing.id)
        .order_by(ListingFavorite.favorited_at.desc())
        .limit(100)
    ).all()
    headers = ["favorited_at", "note", "rank_value", "title", "listing_id"]
    rows = []
    for listing, fav_row, score in rows_db:
        rank_val = float(score.rank_value) if score else None
        rows.append(
            (
                fav_row.favorited_at,
                (fav_row.note or "")[:60],
                rank_val,
                listing.title[:80],
                str(listing.id),
            )
        )
    return headers, rows


CURATED_QUERIES: list[CuratedQuery] = [
    CuratedQuery("counts", "Table row counts", _table_counts),
    CuratedQuery("runs", "Recent workflow runs (20)", _recent_workflow_runs),
    CuratedQuery("steps", "Recent workflow steps (50)", _recent_workflow_steps),
    CuratedQuery("failed_images", "Failed image downloads (100)", _failed_images),
    CuratedQuery("no_scores", "Listings without scores (100)", _listings_without_scores),
    CuratedQuery("top_rank", "Top rank_value (50)", _top_rank_value),
    CuratedQuery("favourites", "All favourites", _favourites),
]


def run_curated_query(query_id: str, session: Session) -> tuple[list[str], list[tuple[Any, ...]]]:
    for query in CURATED_QUERIES:
        if query.query_id == query_id:
            return query.run(session)
    raise ValueError(f"Unknown query_id: {query_id}")
