from __future__ import annotations

import json
from pathlib import Path

from ebay_workflows.operations.match_event_log import log_positive_match


def test_log_positive_match_appends_jsonl(tmp_path: Path) -> None:
    log_file = tmp_path / "matches.jsonl"
    log_positive_match(
        event="title_match",
        phase=2,
        listing_id="listing-1",
        scryfall_id="card-1",
        card_name="Lightning Bolt",
        match_score=0.95,
        source_method="title_match",
        log_path=log_file,
    )
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["match_event"] == "title_match"
    assert payload["scryfall_id"] == "card-1"
    assert payload["card_name"] == "Lightning Bolt"
    assert payload["match_score"] == 0.95


def test_log_positive_match_skips_file_when_path_none() -> None:
    log_positive_match(
        event="faiss_search",
        phase=5,
        listing_id="listing-2",
        scryfall_id="card-2",
        log_path=None,
    )
