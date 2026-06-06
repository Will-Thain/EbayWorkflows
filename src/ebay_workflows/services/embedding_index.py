from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import ScryfallCard
from .openclip_runtime import embed_image_file, embed_image_paths
from .progress_report import emit_progress


@dataclass(slots=True)
class EmbeddingMatch:
    scryfall_id: str
    card_name: str | None
    score: float


def _meta_path(index_path: str) -> Path:
    return Path(f"{index_path}.meta.json")


def index_exists(index_path: str) -> bool:
    return Path(index_path).exists() and _meta_path(index_path).exists()


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


def build_faiss_index(
    session: Session,
    settings: Settings,
    *,
    max_cards: int = 500,
) -> dict[str, Any]:
    """Build FAISS index from Scryfall card art (subset capped by max_cards)."""
    import faiss  # type: ignore[import-not-found]

    cards = (
        session.execute(
            select(ScryfallCard)
            .where(ScryfallCard.image_normal.is_not(None))
            .limit(max_cards)
        )
        .scalars()
        .all()
    )
    if not cards:
        raise ValueError("No Scryfall cards with image_normal found. Run sync-scryfall first.")

    art_dir = Path(settings.image_cache_dir) / "scryfall_art"
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
        pending_paths.append(str(art_path))
        card_ids.append(str(card.id))
        card_names.append(card.name)

    if not pending_paths:
        raise ValueError("Could not embed any Scryfall art images for FAISS index.")

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

    if not matrix_rows:
        raise ValueError("Could not embed any Scryfall art images for FAISS index.")

    matrix = np.vstack(matrix_rows).astype(np.float32)
    dimension = matrix.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(matrix)

    index_path = Path(settings.faiss_index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    _meta_path(str(index_path)).write_text(
        json.dumps(
            {
                "model_name": settings.openclip_model_name,
                "torch_device": settings.torch_device,
                "dimension": dimension,
                "scryfall_ids": indexed_ids,
                "card_names": indexed_names,
            }
        ),
        encoding="utf-8",
    )
    return {
        "cards_considered": len(cards),
        "images_downloaded": downloaded,
        "vectors_indexed": len(matrix_rows),
        "index_path": str(index_path),
        "torch_device": settings.torch_device,
        "embedding_batch_size": settings.embedding_batch_size,
    }


def search_similar_cards(image_path: str, settings: Settings, top_k: int = 5) -> list[EmbeddingMatch]:
    import faiss  # type: ignore[import-not-found]

    index_path = settings.faiss_index_path
    if not index_exists(index_path):
        return []

    meta = json.loads(_meta_path(index_path).read_text(encoding="utf-8"))
    ids: list[str] = meta.get("scryfall_ids", [])
    names: list[str] = meta.get("card_names", [])
    if not ids:
        return []

    query = embed_image_file(image_path, settings)
    index = faiss.read_index(index_path)
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


def apply_embedding_evidence(
    candidates: list[Any],
    matches: list[EmbeddingMatch],
) -> int:
    if not matches:
        return 0

    payload = [
        {"scryfall_id": m.scryfall_id, "card_name": m.card_name, "score": m.score}
        for m in matches
    ]
    top_id = matches[0].scryfall_id
    updated = 0
    for candidate in candidates:
        evidence = dict(candidate.evidence_json or {})
        evidence["faiss_matches"] = payload
        evidence["openclip_model"] = "ViT-B-32"
        if candidate.scryfall_id and str(candidate.scryfall_id) == top_id:
            candidate.confidence_score = min(1.0, float(candidate.confidence_score) + 0.08)
            evidence["embedding_agreement"] = True
        elif candidate.scryfall_id and str(candidate.scryfall_id) != top_id:
            evidence["embedding_agreement"] = False
        candidate.evidence_json = evidence
        updated += 1
    return updated
