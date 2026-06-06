from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterable, Sequence

from rapidfuzz import fuzz, process

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class CardMatchEntry:
    """Lightweight Scryfall card row for title matching."""

    card_id: str
    name: str


@dataclass(frozen=True, slots=True)
class TitleMatchResult:
    """One ranked title match candidate."""

    card_id: str
    card_name: str
    score: float


def tokenize_title(text: str) -> list[str]:
    """Split a title into lowercase alphanumeric tokens (min length 2)."""
    return [token for token in _TOKEN_RE.findall(text.lower()) if len(token) >= 2]


@dataclass
class ScryfallTitleIndex:
    """Inverted token index over Scryfall card names for fast pre-filtering."""

    entries: list[CardMatchEntry]
    lower_names: list[str]
    token_to_indices: dict[str, set[int]]

    @classmethod
    def from_entries(cls, entries: Sequence[CardMatchEntry]) -> ScryfallTitleIndex:
        lower_names = [entry.name.lower() for entry in entries]
        token_to_indices: dict[str, set[int]] = {}
        for index, name in enumerate(lower_names):
            for token in tokenize_title(name):
                token_to_indices.setdefault(token, set()).add(index)
        return cls(entries=list(entries), lower_names=lower_names, token_to_indices=token_to_indices)

    def candidate_indices(self, title: str, *, max_candidates: int) -> list[int]:
        """Return card indices likely to match the listing title."""
        tokens = tokenize_title(title)
        if not tokens:
            return list(range(min(max_candidates, len(self.entries))))

        overlap_scores: Counter[int] = Counter()
        for token in tokens:
            for index in self.token_to_indices.get(token, ()):
                overlap_scores[index] += 1

        if overlap_scores:
            ranked = sorted(
                overlap_scores.keys(),
                key=lambda index: (-overlap_scores[index], len(self.lower_names[index])),
            )
            return ranked[:max_candidates]

        return self._substring_prefilter(title.lower(), max_candidates)

    def _substring_prefilter(self, title_lower: str, max_candidates: int) -> list[int]:
        """Fallback when no token overlap exists (e.g. OCR typos)."""
        tokens = tokenize_title(title_lower)
        if not tokens:
            return list(range(min(max_candidates, len(self.entries))))

        longest = max(tokens, key=len)
        hits: list[int] = []
        for index, name in enumerate(self.lower_names):
            if longest in name or name in title_lower:
                hits.append(index)
            if len(hits) >= max_candidates:
                break
        if hits:
            return hits
        return list(range(min(max_candidates, len(self.entries))))


def rank_title_matches(
    title: str,
    index: ScryfallTitleIndex,
    *,
    top_k: int,
    prefilter_size: int = 512,
    score_cutoff: float = 55.0,
) -> list[TitleMatchResult]:
    """Rank card names against a listing title using pre-filter + RapidFuzz extract."""
    if not index.entries or top_k <= 0:
        return []

    candidate_indices = index.candidate_indices(title, max_candidates=max(prefilter_size, top_k * 20))
    if not candidate_indices:
        return []

    indices = candidate_indices
    names = [index.lower_names[idx] for idx in indices]
    extracted = process.extract(
        title.lower(),
        names,
        scorer=fuzz.WRatio,
        limit=top_k,
        score_cutoff=score_cutoff,
    )

    results: list[TitleMatchResult] = []
    for _name, score, list_pos in extracted:
        entry = index.entries[indices[list_pos]]
        results.append(
            TitleMatchResult(
                card_id=entry.card_id,
                card_name=entry.name,
                score=float(score) / 100.0,
            )
        )
    return results


def best_title_match(
    title: str,
    index: ScryfallTitleIndex,
    *,
    prefilter_size: int = 512,
    score_cutoff: float = 55.0,
) -> TitleMatchResult | None:
    """Return the single best title match above the cutoff."""
    matches = rank_title_matches(
        title,
        index,
        top_k=1,
        prefilter_size=prefilter_size,
        score_cutoff=score_cutoff,
    )
    return matches[0] if matches else None


def match_listings_parallel(
    listings: Iterable[tuple[str, str]],
    index: ScryfallTitleIndex,
    *,
    top_k: int,
    prefilter_size: int,
    max_workers: int,
) -> dict[str, list[TitleMatchResult]]:
    """Match many listing titles in parallel; returns listing_id -> matches."""
    tasks = list(listings)
    if not tasks:
        return {}

    workers = max(1, min(max_workers, len(tasks)))

    def _match_one(item: tuple[str, str]) -> tuple[str, list[TitleMatchResult]]:
        listing_id, title = item
        return listing_id, rank_title_matches(
            title,
            index,
            top_k=top_k,
            prefilter_size=prefilter_size,
        )

    if workers == 1:
        return dict(_match_one(item) for item in tasks)

    results: dict[str, list[TitleMatchResult]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for listing_id, matches in executor.map(_match_one, tasks):
            results[listing_id] = matches
    return results
