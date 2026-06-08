from __future__ import annotations

from types import SimpleNamespace

from mtg_card_recognition.evidence.attach import candidates_for_region_evidence


def _candidate(name: str, set_code: str, collector_number: str, *, rank: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        rank_position=rank,
        scryfall_card=SimpleNamespace(
            name=name,
            set_code=set_code,
            collector_number=collector_number,
        ),
    )


def test_name_only_ocr_skips_ambiguous_reprints() -> None:
    bolt_lea = _candidate("Lightning Bolt", "LEA", "161", rank=1)
    bolt_mkm = _candidate("Lightning Bolt", "MKM", "123", rank=2)
    targets = candidates_for_region_evidence(
        [bolt_lea, bolt_mkm],
        ocr_title="Lightning Bolt",
        fields={"title": ("Lightning Bolt", 0.9)},
        zone_evidence=None,
    )
    assert targets == []


def test_set_collector_routes_to_one_printing() -> None:
    bolt_lea = _candidate("Lightning Bolt", "LEA", "161", rank=1)
    bolt_mkm = _candidate("Lightning Bolt", "MKM", "123", rank=2)
    targets = candidates_for_region_evidence(
        [bolt_lea, bolt_mkm],
        ocr_title="Lightning Bolt",
        fields={
            "title": ("Lightning Bolt", 0.9),
            "set_code": ("LEA", 0.8),
            "collector_number": ("161", 0.8),
        },
        zone_evidence={"bottom_parsed": {"set_code": "LEA", "collector_number": "161"}},
    )
    assert targets == [bolt_lea]


def test_single_name_match_still_attaches() -> None:
    bolt = _candidate("Lightning Bolt", "LEA", "161")
    targets = candidates_for_region_evidence(
        [bolt],
        ocr_title="Lightning Bolt",
        fields={"title": ("Lightning Bolt", 0.9)},
        zone_evidence=None,
    )
    assert targets == [bolt]
