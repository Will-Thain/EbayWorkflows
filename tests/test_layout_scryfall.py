from __future__ import annotations

from mtg_card_recognition.zones.layouts import layout_from_scryfall_payload


def test_layout_from_scryfall_dfc() -> None:
    assert layout_from_scryfall_payload({"layout": "transform"}) == "dfc_front"


def test_layout_from_scryfall_old_frame() -> None:
    assert layout_from_scryfall_payload({"frame": "1993"}) == "old"


def test_layout_from_scryfall_unknown_returns_none() -> None:
    assert layout_from_scryfall_payload({"layout": "normal", "frame": "2015"}) is None
