"""eBay adapter: FAISS index build/search over Postgres Scryfall rows."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from mtg_card_recognition.catalog import PrintingRecord
from mtg_card_recognition.embeddings import faiss_index as _faiss
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings
from ..models import ListingCardCandidate, ScryfallCard
from .progress_report import emit_progress

EmbeddingMatch = _faiss.EmbeddingMatch
clear_faiss_index_cache = _faiss.clear_faiss_index_cache
index_exists = _faiss.index_exists
load_index_meta = _faiss.load_index_meta
indexed_scryfall_ids = _faiss.indexed_scryfall_ids
skipped_scryfall_ids = _faiss.skipped_scryfall_ids
excluded_scryfall_ids = _faiss.excluded_scryfall_ids
faiss_index_crop_mode = _faiss.faiss_index_crop_mode


def _printing_rows(cards: list[ScryfallCard]) -> list[PrintingRecord]:
    return [PrintingRecord.from_mapping(card) for card in cards]


def count_indexable_art_cards(session: Session) -> int:
    return int(
        session.execute(
            select(func.count()).select_from(ScryfallCard).where(ScryfallCard.image_normal.is_not(None))
        ).scalar_one()
    )


def _select_cards_for_batch(
    session: Session,
    *,
    batch_size: int,
    exclude_ids: set[str],
) -> list[ScryfallCard]:
    if not exclude_ids:
        stmt = (
            select(ScryfallCard)
            .where(ScryfallCard.image_normal.is_not(None))
            .order_by(ScryfallCard.id)
            .limit(batch_size)
        )
        return list(session.execute(stmt).scalars().all())

    exclude_uuids = {uuid.UUID(card_id) for card_id in exclude_ids}
    collected: list[ScryfallCard] = []
    cursor: uuid.UUID | None = None
    page_size = max(batch_size, 1000)

    while len(collected) < batch_size:
        stmt = (
            select(ScryfallCard)
            .where(ScryfallCard.image_normal.is_not(None))
            .order_by(ScryfallCard.id)
            .limit(page_size)
        )
        if cursor is not None:
            stmt = stmt.where(ScryfallCard.id > cursor)

        rows = list(session.execute(stmt).scalars().all())
        if not rows:
            break

        for card in rows:
            cursor = card.id
            if card.id in exclude_uuids:
                continue
            collected.append(card)
            if len(collected) >= batch_size:
                break

    return collected


def append_faiss_batch(
    session: Session,
    settings: Settings,
    *,
    batch_size: int,
) -> dict[str, Any]:
    recognition = coerce_recognition_settings(settings)
    index_path = Path(settings.faiss_index_path)
    exclude_ids = excluded_scryfall_ids(str(index_path))
    cards = _select_cards_for_batch(session, batch_size=batch_size, exclude_ids=exclude_ids)
    if not cards:
        return {
            "batch_complete": True,
            "cards_considered": 0,
            "vectors_indexed": 0,
            "vectors_total": len(indexed_scryfall_ids(str(index_path))),
            "index_path": str(index_path),
        }

    printings = _printing_rows(cards)
    pending_paths, card_ids, card_names, downloaded = _faiss.prepare_art_paths(printings, recognition)
    if not pending_paths:
        _faiss.append_skipped_ids(index_path, [str(card.id) for card in cards])
        remaining = _select_cards_for_batch(
            session,
            batch_size=1,
            exclude_ids=excluded_scryfall_ids(str(index_path)),
        )
        return {
            "batch_complete": not remaining,
            "cards_considered": len(cards),
            "images_downloaded": downloaded,
            "vectors_indexed": 0,
            "vectors_total": len(indexed_scryfall_ids(str(index_path))),
            "index_path": str(index_path),
            "skipped_unembeddable": [str(card.id) for card in cards],
        }

    matrix_rows, new_ids, new_names = _faiss.embed_art_paths(
        pending_paths,
        card_ids,
        card_names,
        recognition,
        on_progress=lambda done, total, unit: emit_progress(done, total, unit=unit),
    )
    if not matrix_rows:
        _faiss.append_skipped_ids(index_path, card_ids)
        remaining = _select_cards_for_batch(
            session,
            batch_size=1,
            exclude_ids=excluded_scryfall_ids(str(index_path)),
        )
        return {
            "batch_complete": not remaining,
            "cards_considered": len(cards),
            "images_downloaded": downloaded,
            "vectors_indexed": 0,
            "vectors_total": len(indexed_scryfall_ids(str(index_path))),
            "index_path": str(index_path),
            "skipped_unembeddable": card_ids,
        }

    vectors_added = _faiss.write_faiss_index(
        index_path,
        matrix_rows,
        new_ids,
        new_names,
        recognition,
        append=bool(exclude_ids),
    )
    return {
        "batch_complete": False,
        "cards_considered": len(cards),
        "images_downloaded": downloaded,
        "vectors_indexed": vectors_added,
        "vectors_total": len(indexed_scryfall_ids(str(index_path))),
        "index_path": str(index_path),
        "torch_device": settings.torch_device,
        "embedding_batch_size": settings.embedding_batch_size,
    }


def build_faiss_index(
    session: Session,
    settings: Settings,
    *,
    max_cards: int = 500,
    append: bool = False,
) -> dict[str, Any]:
    if append:
        return append_faiss_batch(session, settings, batch_size=max_cards)

    cards = _select_cards_for_batch(session, batch_size=max_cards, exclude_ids=set())
    if not cards:
        raise ValueError("No Scryfall cards with image_normal found. Run sync-scryfall first.")

    return _faiss.build_index_from_printings(
        _printing_rows(cards),
        coerce_recognition_settings(settings),
        append=False,
        on_progress=lambda done, total, unit: emit_progress(done, total, unit=unit),
    )


def build_faiss_index_all_batches(
    session: Session,
    settings: Settings,
    *,
    batch_size: int,
    max_batches: int | None = None,
) -> dict[str, Any]:
    batches_run = 0
    vectors_added_total = 0
    last_summary: dict[str, Any] = {}
    indexable_total = count_indexable_art_cards(session)

    while True:
        if max_batches is not None and batches_run >= max_batches:
            break

        summary = append_faiss_batch(session, settings, batch_size=batch_size)
        last_summary = summary
        if summary.get("batch_complete"):
            break

        batches_run += 1
        vectors_added_total += int(summary.get("vectors_indexed", 0))
        vectors_total = int(summary.get("vectors_total", 0))
        emit_progress(vectors_total, indexable_total, unit="faiss-total")

    return {
        "batches_run": batches_run,
        "vectors_added_total": vectors_added_total,
        "vectors_total": int(
            last_summary.get("vectors_total", len(indexed_scryfall_ids(settings.faiss_index_path)))
        ),
        "indexable_total": indexable_total,
        "index_path": settings.faiss_index_path,
        "complete": bool(last_summary.get("batch_complete", False)),
    }


def search_similar_cards(image_path: str, settings: Settings, top_k: int = 5) -> list[EmbeddingMatch]:
    return _faiss.search_similar_cards(
        image_path,
        coerce_recognition_settings(settings),
        top_k=top_k,
    )


def propose_embedding_candidates(
    session: Session,
    listing_id: Any,
    candidates: list[ListingCardCandidate],
    matches: list[EmbeddingMatch],
    settings: Settings,
) -> int:
    """Insert a FAISS top-1 candidate when it is absent from Phase 2 title matches."""
    if not settings.faiss_propose_candidates or not matches:
        return 0

    top = matches[0]
    if top.score < settings.image_evidence_min_faiss_score:
        return 0

    existing_ids = {str(candidate.scryfall_id) for candidate in candidates if candidate.scryfall_id}
    if top.scryfall_id in existing_ids:
        return 0

    try:
        proposed_id = uuid.UUID(top.scryfall_id)
    except ValueError:
        return 0

    if session.get(ScryfallCard, proposed_id) is None:
        return 0

    existing_faiss = session.execute(
        select(ListingCardCandidate.id)
        .where(
            ListingCardCandidate.listing_id == listing_id,
            ListingCardCandidate.scryfall_id == proposed_id,
            ListingCardCandidate.source_method == "faiss_proposal",
        )
        .limit(1)
    ).first()
    if existing_faiss is not None:
        return 0

    next_rank = max((int(c.rank_position) for c in candidates), default=0) + 1
    payload = [
        {"scryfall_id": m.scryfall_id, "card_name": m.card_name, "score": m.score}
        for m in matches
    ]
    candidate = ListingCardCandidate(
        listing_id=listing_id,
        source_method="faiss_proposal",
        scryfall_id=proposed_id,
        match_score=top.score,
        confidence_score=min(0.45, float(top.score)),
        rank_position=next_rank,
        evidence_json={
            "method": "faiss_proposal",
            "faiss_matches": payload,
            "faiss_score": top.score,
            "pricing_eligible": False,
            "pricing_reject_reason": "faiss_proposal_unverified",
        },
    )
    session.add(candidate)
    session.flush()
    candidates.append(candidate)
    from .match_event_log import log_positive_match, match_log_path

    log_positive_match(
        event="faiss_proposal",
        phase=5,
        listing_id=str(listing_id),
        scryfall_id=top.scryfall_id,
        card_name=top.card_name,
        match_score=float(top.score),
        source_method="faiss_proposal",
        log_path=match_log_path(settings),
    )
    return 1


def apply_embedding_evidence(
    candidates: list[Any],
    matches: list[EmbeddingMatch],
    *,
    listing_id: Any | None = None,
    settings: Settings | None = None,
) -> int:
    """Attach FAISS hits only to candidates whose Scryfall ID appears in the region matches."""
    if not matches:
        return 0

    payload = [
        {"scryfall_id": m.scryfall_id, "card_name": m.card_name, "score": m.score}
        for m in matches
    ]
    top_id = matches[0].scryfall_id
    updated = 0
    for candidate in candidates:
        if not candidate.scryfall_id:
            continue
        cid = str(candidate.scryfall_id)
        region_match = next((m for m in matches if m.scryfall_id == cid), None)
        if region_match is None:
            continue

        evidence = dict(candidate.evidence_json or {})
        evidence["faiss_matches"] = payload
        evidence["faiss_score"] = region_match.score
        evidence["openclip_model"] = "ViT-B-32"
        evidence["embedding_agreement"] = cid == top_id
        if cid == top_id:
            candidate.confidence_score = min(1.0, float(candidate.confidence_score) + 0.08)
        candidate.evidence_json = evidence
        if settings is not None and listing_id is not None:
            from .match_event_log import log_positive_match, match_log_path

            card = getattr(candidate, "scryfall_card", None)
            log_positive_match(
                event="faiss_attach",
                phase=5,
                listing_id=str(listing_id),
                scryfall_id=cid,
                card_name=getattr(card, "name", None) or region_match.card_name,
                match_score=float(region_match.score),
                source_method=getattr(candidate, "source_method", None),
                embedding_agreement=cid == top_id,
                log_path=match_log_path(settings),
            )
        updated += 1
    return updated
