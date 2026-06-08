from __future__ import annotations

from ebay_workflows.services.card_identifiers import (
    build_set_collector_index,
    lookup_card_by_identifiers,
    parse_card_identifiers,
)
from ebay_workflows.services.title_match import (
    CardMatchEntry,
    ScryfallTitleIndex,
    best_card_match_for_text,
)


def test_parse_set_collector_from_title() -> None:
    parsed = parse_card_identifiers("Lightning Bolt M11 232 LP")
    assert parsed.set_code == "M11"
    assert parsed.collector_number == "232"


def test_parse_collector_from_fraction() -> None:
    parsed = parse_card_identifiers("Sol Ring C21 232/381 NM")
    assert parsed.set_code == "C21"
    assert parsed.collector_number == "232"


def test_lookup_exact_set_collector() -> None:
    index = build_set_collector_index([("card-1", "M11", "232")])
    parsed = parse_card_identifiers("M11 232")
    assert lookup_card_by_identifiers(parsed, index) == "card-1"


def test_best_card_match_prefers_set_collector() -> None:
    entries = [
        CardMatchEntry("1", "Lightning Bolt", "M11", "232"),
        CardMatchEntry("2", "Lightning Strike", "M11", "150"),
    ]
    title_index = ScryfallTitleIndex.from_entries(entries)
    set_index = build_set_collector_index([("1", "M11", "232"), ("2", "M11", "150")])
    card_by_id = {"1": type("Card", (), {"name": "Lightning Bolt"})(), "2": type("Card", (), {"name": "Lightning Strike"})()}

    result = best_card_match_for_text(
        "Lightning Bolt M11 232",
        title_index,
        set_index,
        card_by_id,
        prefilter_size=10,
        score_cutoff=65.0,
    )
    assert result is not None
    assert result.card_id == "1"
    assert result.match_method == "set_collector"
    assert result.score == 1.0
