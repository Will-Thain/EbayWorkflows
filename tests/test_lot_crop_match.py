from __future__ import annotations

from dataclasses import dataclass, replace

from mtg_card_recognition.config import RecognitionSettings
from mtg_card_recognition.pipeline.lot_match import (
    _apply_lot_crop_confidence_floor,
    resolve_lot_crop_match,
)
from mtg_card_recognition.title.match import (
    CardMatchEntry,
    ScryfallTitleIndex,
    TitleMatchResult,
)


@dataclass
class _FakeCard:
    id: str
    name: str


@dataclass
class _FaissMatch:
    scryfall_id: str
    card_name: str
    score: float


def _settings(**overrides) -> RecognitionSettings:
    base = RecognitionSettings(image_cache_dir=".")
    return replace(base, **overrides)


def test_confidence_floor_rejects_faiss_override_when_title_disagrees() -> None:
    card_b = _FakeCard("bbb", "Wrong Token")
    title_result = TitleMatchResult(
        card_id="aaa",
        card_name="Lightning Bolt",
        score=0.70,
        match_method="fuzzy_title",
    )
    evidence = {
        "match_method": "faiss_override",
        "faiss_top_scryfall_id": "bbb",
        "faiss_top_score": 0.80,
        "faiss_override": True,
    }

    chosen, score, out = _apply_lot_crop_confidence_floor(
        evidence=evidence,
        title_result=title_result,
        chosen_card=card_b,
        chosen_score=0.80,
        settings=_settings(),
    )

    assert chosen is None
    assert score == 0.0
    assert out["lot_crop_rejected"] == "faiss_title_disagreement"


def test_confidence_floor_allows_set_collector() -> None:
    card = _FakeCard("aaa", "Lightning Bolt")
    evidence = {"match_method": "set_collector"}

    chosen, score, out = _apply_lot_crop_confidence_floor(
        evidence=evidence,
        title_result=None,
        chosen_card=card,
        chosen_score=1.0,
        settings=_settings(lot_crop_min_combined_confidence=0.99),
    )

    assert chosen is card
    assert score == 1.0
    assert "lot_crop_rejected" not in out


def test_confidence_floor_rejects_low_combined_when_faiss_disagrees() -> None:
    card = _FakeCard("aaa", "Lightning Bolt")
    title_result = TitleMatchResult(
        card_id="aaa",
        card_name="Lightning Bolt",
        score=0.50,
        match_method="fuzzy_title",
    )
    evidence = {
        "match_method": "fuzzy_title",
        "faiss_top_scryfall_id": "bbb",
        "faiss_top_score": 0.70,
    }

    chosen, score, out = _apply_lot_crop_confidence_floor(
        evidence=evidence,
        title_result=title_result,
        chosen_card=card,
        chosen_score=0.50,
        settings=_settings(lot_crop_min_combined_confidence=0.42),
    )

    assert chosen is None
    assert out["lot_crop_rejected"] == "faiss_title_disagreement_low_combined"


def test_resolve_lot_crop_match_faiss_only_rejected_on_disagreement(tmp_path) -> None:
    crop = tmp_path / "crop.jpg"
    crop.write_bytes(b"\xff\xd8\xff")
    card_a = _FakeCard("aaa", "Lightning Bolt")
    card_b = _FakeCard("bbb", "Wrong Token")
    card_by_id = {"aaa": card_a, "bbb": card_b}
    title_index = ScryfallTitleIndex.from_entries(
        [CardMatchEntry(card_id="aaa", name="Lightning Bolt")]
    )

    def search_similar(_path: str) -> list[_FaissMatch]:
        return [_FaissMatch("bbb", "Wrong Token", 0.85)]

    card, score, evidence = resolve_lot_crop_match(
        ocr_title="Lightning Bolt",
        crop_path=str(crop),
        title_index=title_index,
        set_collector_index={},
        card_by_id=card_by_id,
        settings=_settings(card_zone_ocr_enabled=False),
        faiss_enabled=True,
        search_similar=search_similar,
        index_ready=lambda: True,
    )

    assert card is None
    assert score == 0.0
    assert evidence.get("lot_crop_rejected") == "faiss_title_disagreement"
