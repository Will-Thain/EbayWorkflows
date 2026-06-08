from __future__ import annotations

from pathlib import Path

import pytest

from ebay_workflows.services.card_identifiers import merge_identifiers, parse_bottom_strip
from ebay_workflows.services.card_zones import STANDARD_MTG_ZONES, extract_zone_crops, faiss_query_path


def test_parse_bottom_strip_finds_collector_and_set() -> None:
    parsed = parse_bottom_strip("R Kev Walker 233/297 • MKM EN © 2024 Wizards")
    assert parsed.collector_number == "233"
    assert parsed.set_code == "MKM"


def test_merge_identifiers_prefers_first_non_empty() -> None:
    from ebay_workflows.services.card_identifiers import ParsedCardIdentifiers

    merged = merge_identifiers(
        ParsedCardIdentifiers(set_code="MKM", collector_number=None),
        ParsedCardIdentifiers(set_code="ABC", collector_number="12"),
    )
    assert merged.set_code == "MKM"
    assert merged.collector_number == "12"


def test_extract_zone_crops_creates_name_art_bottom(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    import numpy as np  # type: ignore[import-not-found]

    card = np.full((700, 500, 3), 255, dtype=np.uint8)
    cv2.rectangle(card, (0, 0), (499, 699), (0, 0, 0), 2)
    cv2.putText(card, "Lightning Bolt", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    cv2.putText(card, "233/297 MKM", (20, 670), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    card_path = tmp_path / "card.jpg"
    cv2.imwrite(str(card_path), card)

    crops = extract_zone_crops(str(card_path), str(tmp_path / "zones"))
    assert crops.name_path and Path(crops.name_path).is_file()
    assert crops.art_path and Path(crops.art_path).is_file()
    assert crops.bottom_path and Path(crops.bottom_path).is_file()
    assert crops.set_symbol_path and Path(crops.set_symbol_path).is_file()
    assert crops.mana_cost_path and Path(crops.mana_cost_path).is_file()
    assert faiss_query_path(crops, use_art_zone=True) == crops.art_path
    assert faiss_query_path(crops, use_art_zone=False) == str(card_path)


def test_standard_zones_cover_key_layout_areas() -> None:
    assert "name" in STANDARD_MTG_ZONES
    assert "art" in STANDARD_MTG_ZONES
    assert "bottom" in STANDARD_MTG_ZONES
    art = STANDARD_MTG_ZONES["art"]
    assert 0.1 < art.y < 0.2
    assert art.h > 0.3
