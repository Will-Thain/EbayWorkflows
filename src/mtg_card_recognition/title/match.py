from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from rapidfuzz import fuzz, process

from ..identifiers import (
    ParsedCardIdentifiers,
    lookup_card_by_identifiers,
    parse_card_identifiers,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class CardMatchEntry:
    """Lightweight Scryfall card row for title matching."""

    card_id: str
    name: str
    set_code: str | None = None
    collector_number: str | None = None


@dataclass(frozen=True, slots=True)
class TitleMatchResult:
    """One ranked title match candidate."""

    card_id: str
    card_name: str
    score: float
    match_method: str = "fuzzy_title"


def tokenize_title(text: str) -> list[str]:
    """Split a title into lowercase alphanumeric tokens (min length 2)."""
    return [token for token in _TOKEN_RE.findall(text.lower()) if len(token) >= 2]


@dataclass
class ScryfallTitleIndex:
    """Inverted token index over Scryfall card names for fast pre-filtering."""

    entries: list[CardMatchEntry]
    lower_names: list[str]
    set_codes: list[str | None]
    token_to_indices: dict[str, set[int]]

    @classmethod
    def from_entries(cls, entries: Sequence[CardMatchEntry]) -> ScryfallTitleIndex:
        lower_names = [entry.name.lower() for entry in entries]
        set_codes = [
            entry.set_code.lower() if entry.set_code else None for entry in entries
        ]
        token_to_indices: dict[str, set[int]] = {}
        for index, name in enumerate(lower_names):
            for token in tokenize_title(name):
                token_to_indices.setdefault(token, set()).add(index)
        return cls(
            entries=list(entries),
            lower_names=lower_names,
            set_codes=set_codes,
            token_to_indices=token_to_indices,
        )

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
    required_set_code: str | None = None,
) -> list[TitleMatchResult]:
    """Rank card names against a listing title using pre-filter + RapidFuzz extract."""
    if not index.entries or top_k <= 0:
        return []

    candidate_indices = index.candidate_indices(title, max_candidates=max(prefilter_size, top_k * 20))
    if not candidate_indices:
        return []

    if required_set_code:
        normalized_set = required_set_code.lower()
        filtered = [idx for idx in candidate_indices if index.set_codes[idx] == normalized_set]
        if filtered:
            candidate_indices = filtered

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
    required_set_code: str | None = None,
) -> TitleMatchResult | None:
    """Return the single best title match above the cutoff."""
    matches = rank_title_matches(
        title,
        index,
        top_k=1,
        prefilter_size=prefilter_size,
        score_cutoff=score_cutoff,
        required_set_code=required_set_code,
    )
    return matches[0] if matches else None


def best_card_match_for_text(
    text: str,
    index: ScryfallTitleIndex,
    set_collector_index: dict[tuple[str, str], str],
    card_by_id: dict[str, Any],
    *,
    prefilter_size: int,
    score_cutoff: float,
    extra_identifiers: ParsedCardIdentifiers | None = None,
) -> TitleMatchResult | None:
    """Resolve a card using set/collector identifiers first, then fuzzy title match."""
    identifiers = extra_identifiers or parse_card_identifiers(text)
    exact_id = lookup_card_by_identifiers(identifiers, set_collector_index)
    if exact_id and exact_id in card_by_id:
        card = card_by_id[exact_id]
        return TitleMatchResult(
            card_id=exact_id,
            card_name=card.name if hasattr(card, "name") else str(card),
            score=1.0,
            match_method="set_collector",
        )

    required_set = identifiers.set_code.lower() if identifiers.set_code else None
    return best_title_match(
        text,
        index,
        prefilter_size=prefilter_size,
        score_cutoff=score_cutoff,
        required_set_code=required_set,
    )


def match_listings_parallel(
    listings: Iterable[tuple[str, str]],
    index: ScryfallTitleIndex,
    *,
    top_k: int,
    prefilter_size: int,
    max_workers: int,
    score_cutoff: float = 55.0,
    set_collector_index: dict[tuple[str, str], str] | None = None,
    card_by_id: dict[str, Any] | None = None,
) -> dict[str, list[TitleMatchResult]]:
    """Match many listing titles in parallel; returns listing_id -> matches."""
    tasks = list(listings)
    if not tasks:
        return {}

    workers = max(1, min(max_workers, len(tasks)))

    def _match_one(item: tuple[str, str]) -> tuple[str, list[TitleMatchResult]]:
        listing_id, title = item
        if set_collector_index is not None and card_by_id is not None:
            exact = best_card_match_for_text(
                title,
                index,
                set_collector_index,
                card_by_id,
                prefilter_size=prefilter_size,
                score_cutoff=score_cutoff,
            )
            parsed = parse_card_identifiers(title)
            required_set = parsed.set_code.lower() if parsed.set_code else None
            if exact is not None:
                ranked = rank_title_matches(
                    title,
                    index,
                    top_k=top_k,
                    prefilter_size=prefilter_size,
                    score_cutoff=score_cutoff,
                    required_set_code=required_set,
                )
                merged: list[TitleMatchResult] = [exact]
                for match in ranked:
                    if match.card_id != exact.card_id:
                        merged.append(match)
                    if len(merged) >= top_k:
                        break
                return listing_id, merged[:top_k]

        parsed = parse_card_identifiers(title)
        required_set = parsed.set_code.lower() if parsed.set_code else None
        return listing_id, rank_title_matches(
            title,
            index,
            top_k=top_k,
            prefilter_size=prefilter_size,
            score_cutoff=score_cutoff,
            required_set_code=required_set,
        )

    if workers == 1:
        return dict(_match_one(item) for item in tasks)

    results: dict[str, list[TitleMatchResult]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for listing_id, matches in executor.map(_match_one, tasks):
            results[listing_id] = matches
    return results
