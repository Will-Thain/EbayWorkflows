from __future__ import annotations

from ebay_workflows.services.title_match import (
    CardMatchEntry,
    ScryfallTitleIndex,
    rank_title_matches,
    tokenize_title,
)


def test_tokenize_title_filters_short_tokens() -> None:
    assert tokenize_title("MTG Lightning Bolt LP") == ["mtg", "lightning", "bolt", "lp"]


def test_prefilter_narrows_candidates_before_fuzzy() -> None:
    entries = [
        CardMatchEntry("1", "Lightning Bolt"),
        CardMatchEntry("2", "Sol Ring"),
        CardMatchEntry("3", "Counterspell"),
    ]
    index = ScryfallTitleIndex.from_entries(entries)
    candidates = index.candidate_indices("MTG Lightning Bolt M11 LP", max_candidates=10)
    assert 0 in candidates
    assert 1 not in candidates or len(candidates) <= 2


def test_rank_title_matches_returns_best_card() -> None:
    entries = [
        CardMatchEntry("1", "Lightning Bolt"),
        CardMatchEntry("2", "Sol Ring"),
        CardMatchEntry("3", "Lightning Strike"),
    ]
    index = ScryfallTitleIndex.from_entries(entries)
    matches = rank_title_matches(
        "MTG Lightning Bolt M11 LP",
        index,
        top_k=2,
        prefilter_size=10,
    )
    assert matches
    assert matches[0].card_name == "Lightning Bolt"
    assert matches[0].score >= 0.55


def test_rank_title_matches_respects_top_k() -> None:
    entries = [CardMatchEntry(str(i), f"Card {i}") for i in range(20)]
    index = ScryfallTitleIndex.from_entries(entries)
    matches = rank_title_matches("Card 1", index, top_k=3, prefilter_size=5)
    assert len(matches) <= 3
