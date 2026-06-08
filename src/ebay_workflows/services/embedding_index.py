from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import ListingCardCandidate, ScryfallCard
from mtg_card_recognition.zones.layouts import layout_from_scryfall_payload
from .card_zones import extract_art_zone_from_card_image
from .openclip_runtime import embed_image_file, embed_image_paths
from .progress_report import emit_progress


@dataclass(slots=True)
class EmbeddingMatch:
    scryfall_id: str
    card_name: str | None
    score: float


_FAISS_INDEX_CACHE: dict[str, tuple[Any, dict[str, Any]]] = {}


def clear_faiss_index_cache() -> None:
    """Drop cached FAISS handles (for tests or after index rebuild)."""
    _FAISS_INDEX_CACHE.clear()


def _load_faiss_index(index_path: str) -> tuple[Any, dict[str, Any]] | None:
    import faiss  # type: ignore[import-not-found]

    resolved = str(Path(index_path).resolve())
    if resolved in _FAISS_INDEX_CACHE:
        return _FAISS_INDEX_CACHE[resolved]

    if not index_exists(resolved):
        return None

    index = faiss.read_index(resolved)
    meta = json.loads(_meta_path(resolved).read_text(encoding="utf-8"))
    _FAISS_INDEX_CACHE[resolved] = (index, meta)
    return index, meta


def _meta_path(index_path: str) -> Path:
    return Path(f"{index_path}.meta.json")


def index_exists(index_path: str) -> bool:
    return Path(index_path).exists() and _meta_path(index_path).exists()


def load_index_meta(index_path: str) -> dict[str, Any] | None:
    meta_file = _meta_path(index_path)
    if not meta_file.exists():
        return None
    return json.loads(meta_file.read_text(encoding="utf-8"))


def indexed_scryfall_ids(index_path: str) -> set[str]:
    meta = load_index_meta(index_path)
    if not meta:
        return set()
    return {str(card_id) for card_id in meta.get("scryfall_ids", [])}


def skipped_scryfall_ids(index_path: str) -> set[str]:
    meta = load_index_meta(index_path)
    if not meta:
        return set()
    return {str(card_id) for card_id in meta.get("skipped_scryfall_ids", [])}


def excluded_scryfall_ids(index_path: str) -> set[str]:
    return indexed_scryfall_ids(index_path) | skipped_scryfall_ids(index_path)


def _append_skipped_ids(index_path: Path, card_ids: list[str]) -> None:
    if not card_ids:
        return
    meta_file = _meta_path(str(index_path))
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    skipped = {str(card_id) for card_id in meta.get("skipped_scryfall_ids", [])}
    skipped.update(card_ids)
    meta["skipped_scryfall_ids"] = sorted(skipped)
    meta_file.write_text(json.dumps(meta), encoding="utf-8")


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


def _download_art(url: str, dest: Path, timeout_ms: int) -> bool:
    try:
        with httpx.Client(timeout=timeout_ms / 1000) as client:
            response = client.get(url)
            response.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(response.content)
        return True
    except (httpx.HTTPError, OSError):
        return False


def faiss_index_crop_mode(settings: Settings) -> str:
    """Return index crop mode; art_zone matches CARD_ZONE_FAISS query crops."""
    if settings.faiss_index_use_art_zone and settings.card_zone_faiss_enabled:
        return "art_zone"
    return "full_card"


def _prepare_art_paths(
    cards: list[ScryfallCard],
    settings: Settings,
) -> tuple[list[str], list[str], list[str], int]:
    art_dir = Path(settings.image_cache_dir) / "scryfall_art"
    art_zone_dir = Path(settings.image_cache_dir) / "scryfall_art_zones"
    use_art_zone = faiss_index_crop_mode(settings) == "art_zone"
    pending_paths: list[str] = []
    card_ids: list[str] = []
    card_names: list[str] = []
    downloaded = 0

    for card in cards:
        if not card.image_normal:
            continue
        art_path = art_dir / f"{card.id}.jpg"
        if not art_path.exists():
            ok = _download_art(card.image_normal, art_path, settings.image_download_timeout_ms)
            if ok:
                downloaded += 1
            time.sleep(0.05)
        if not art_path.exists():
            continue

        embed_path = art_path
        if use_art_zone:
            zone_path = art_zone_dir / f"{card.id}_art.jpg"
            if not zone_path.is_file():
                layout_hint = layout_from_scryfall_payload(card.raw_payload_json)
                extracted = extract_art_zone_from_card_image(
                    str(art_path),
                    str(zone_path),
                    align_enabled=settings.card_zone_align_enabled,
                    scryfall_layout=layout_hint,
                )
                if not extracted:
                    continue
            embed_path = zone_path

        pending_paths.append(str(embed_path))
        card_ids.append(str(card.id))
        card_names.append(card.name)

    return pending_paths, card_ids, card_names, downloaded


def _embed_art_paths(
    pending_paths: list[str],
    card_ids: list[str],
    card_names: list[str],
    settings: Settings,
) -> tuple[list[np.ndarray], list[str], list[str]]:
    batch_size = max(1, settings.embedding_batch_size)
    matrix_rows: list[np.ndarray] = []
    indexed_ids: list[str] = []
    indexed_names: list[str] = []
    total_paths = len(pending_paths)

    if total_paths:
        emit_progress(0, total_paths, unit="embeddings")

    for start in range(0, len(pending_paths), batch_size):
        chunk_paths = pending_paths[start : start + batch_size]
        chunk_ids = card_ids[start : start + batch_size]
        chunk_names = card_names[start : start + batch_size]
        try:
            vectors = embed_image_paths(chunk_paths, settings)
            for vector, card_id, card_name in zip(vectors, chunk_ids, chunk_names, strict=True):
                matrix_rows.append(vector)
                indexed_ids.append(card_id)
                indexed_names.append(card_name)
        except Exception:  # noqa: BLE001
            for path, card_id, card_name in zip(chunk_paths, chunk_ids, chunk_names, strict=True):
                try:
                    vector = embed_image_file(path, settings)
                except Exception:  # noqa: BLE001
                    continue
                matrix_rows.append(vector[0])
                indexed_ids.append(card_id)
                indexed_names.append(card_name)

        done = min(start + len(chunk_paths), total_paths)
        if done % (batch_size * 5) == 0 or done == total_paths:
            emit_progress(done, total_paths, unit="embeddings")

    return matrix_rows, indexed_ids, indexed_names


def _write_faiss_index(
    index_path: Path,
    matrix_rows: list[np.ndarray],
    indexed_ids: list[str],
    indexed_names: list[str],
    settings: Settings,
    *,
    append: bool,
) -> int:
    import faiss  # type: ignore[import-not-found]

    if not matrix_rows:
        return 0

    matrix = np.vstack(matrix_rows).astype(np.float32)
    dimension = matrix.shape[1]
    index_path.parent.mkdir(parents=True, exist_ok=True)

    if append and index_exists(str(index_path)):
        index = faiss.read_index(str(index_path))
        meta = load_index_meta(str(index_path)) or {}
        if int(index.d) != dimension:
            raise ValueError(
                f"FAISS dimension mismatch: index has {index.d}, new vectors have {dimension}"
            )
        existing_ids = [str(card_id) for card_id in meta.get("scryfall_ids", [])]
        existing_names = [str(name) for name in meta.get("card_names", [])]
        index.add(matrix)
        indexed_ids = existing_ids + indexed_ids
        indexed_names = existing_names + indexed_names
    else:
        index = faiss.IndexFlatIP(dimension)
        index.add(matrix)

    faiss.write_index(index, str(index_path))
    crop_mode = faiss_index_crop_mode(settings)
    _meta_path(str(index_path)).write_text(
        json.dumps(
            {
                "model_name": settings.openclip_model_name,
                "torch_device": settings.torch_device,
                "dimension": dimension,
                "index_crop_mode": crop_mode,
                "scryfall_ids": indexed_ids,
                "card_names": indexed_names,
            }
        ),
        encoding="utf-8",
    )
    return len(matrix_rows)


def append_faiss_batch(
    session: Session,
    settings: Settings,
    *,
    batch_size: int,
) -> dict[str, Any]:
    """Index the next batch of Scryfall art, appending to any existing FAISS index."""
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

    pending_paths, card_ids, card_names, downloaded = _prepare_art_paths(cards, settings)
    if not pending_paths:
        _append_skipped_ids(index_path, [str(card.id) for card in cards])
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

    matrix_rows, new_ids, new_names = _embed_art_paths(pending_paths, card_ids, card_names, settings)
    if not matrix_rows:
        _append_skipped_ids(index_path, card_ids)
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

    vectors_added = _write_faiss_index(
        index_path,
        matrix_rows,
        new_ids,
        new_names,
        settings,
        append=bool(exclude_ids),
    )
    total_vectors = len(indexed_scryfall_ids(str(index_path)))

    return {
        "batch_complete": False,
        "cards_considered": len(cards),
        "images_downloaded": downloaded,
        "vectors_indexed": vectors_added,
        "vectors_total": total_vectors,
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
    """Build or replace FAISS index from the first max_cards Scryfall art images."""
    if append:
        return append_faiss_batch(session, settings, batch_size=max_cards)

    cards = _select_cards_for_batch(session, batch_size=max_cards, exclude_ids=set())
    if not cards:
        raise ValueError("No Scryfall cards with image_normal found. Run sync-scryfall first.")

    pending_paths, card_ids, card_names, downloaded = _prepare_art_paths(cards, settings)
    if not pending_paths:
        raise ValueError("Could not embed any Scryfall art images for FAISS index.")

    matrix_rows, indexed_ids, indexed_names = _embed_art_paths(
        pending_paths, card_ids, card_names, settings
    )
    if not matrix_rows:
        raise ValueError("Could not embed any Scryfall art images for FAISS index.")

    index_path = Path(settings.faiss_index_path)
    vectors_indexed = _write_faiss_index(
        index_path,
        matrix_rows,
        indexed_ids,
        indexed_names,
        settings,
        append=False,
    )
    return {
        "cards_considered": len(cards),
        "images_downloaded": downloaded,
        "vectors_indexed": vectors_indexed,
        "index_path": str(index_path),
        "torch_device": settings.torch_device,
        "embedding_batch_size": settings.embedding_batch_size,
    }


def build_faiss_index_all_batches(
    session: Session,
    settings: Settings,
    *,
    batch_size: int,
    max_batches: int | None = None,
) -> dict[str, Any]:
    """Append batch_size cards per iteration until all indexable art is embedded."""
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
        "vectors_total": int(last_summary.get("vectors_total", len(indexed_scryfall_ids(settings.faiss_index_path)))),
        "indexable_total": indexable_total,
        "index_path": settings.faiss_index_path,
        "complete": bool(last_summary.get("batch_complete", False)),
    }


def search_similar_cards(image_path: str, settings: Settings, top_k: int = 5) -> list[EmbeddingMatch]:
    index_path = settings.faiss_index_path
    loaded = _load_faiss_index(index_path)
    if loaded is None:
        return []

    index, meta = loaded
    expected_mode = faiss_index_crop_mode(settings)
    indexed_mode = meta.get("index_crop_mode", "full_card")
    if indexed_mode != expected_mode:
        # Mismatch reduces accuracy; caller should rebuild index with matching crop mode.
        pass

    ids: list[str] = meta.get("scryfall_ids", [])
    names: list[str] = meta.get("card_names", [])
    if not ids:
        return []

    query = embed_image_file(image_path, settings)
    k = min(top_k, len(ids))
    scores, indices = index.search(query, k)

    matches: list[EmbeddingMatch] = []
    for score, idx in zip(scores[0], indices[0], strict=False):
        if idx < 0 or idx >= len(ids):
            continue
        matches.append(
            EmbeddingMatch(
                scryfall_id=ids[idx],
                card_name=names[idx] if idx < len(names) else None,
                score=float(score),
            )
        )
    return matches


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
    candidates.append(candidate)
    return 1


def apply_embedding_evidence(
    candidates: list[Any],
    matches: list[EmbeddingMatch],
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
        updated += 1
    return updated
