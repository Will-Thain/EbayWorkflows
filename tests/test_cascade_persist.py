"""Tests for v0.3 cascade → Phase 5 persistence views."""

from __future__ import annotations

from mtg_card_recognition.catalog.lookup import CatalogIndex
from mtg_card_recognition.catalog.printing import PrintingRecord

from ebay_workflows.recognition.catalog_index import catalog_from_scryfall_rows
from ebay_workflows.recognition.cascade_persist import fields_from_signals


def test_catalog_from_scryfall_rows() -> None:
    catalog = catalog_from_scryfall_rows(
        [
            {
                "id": "inv-201",
                "name": "Magnigoth Treefolk",
                "set_code": "inv",
                "collector_number": "201",
                "type_line": "Creature — Treefolk",
            }
        ]
    )
    assert isinstance(catalog, CatalogIndex)
    assert catalog.lookup_set_collector("inv", "201")


def test_fields_from_signals_maps_bottom() -> None:
    fields = fields_from_signals(
        {
            "bottom_parsed": {
                "set_code": "inv",
                "collector_number": "201",
                "ocr_confidence": 0.72,
            },
            "name_ocr": "Magnigoth Treefolk",
        }
    )
    assert fields["set_code"] == ("inv", 0.72)
    assert fields["collector_number"] == ("201", 0.72)
    assert fields["title"] == ("Magnigoth Treefolk", 0.8)


def test_printing_record_from_mapping() -> None:
    record = PrintingRecord.from_mapping(
        {"id": "abc", "name": "Bolt", "set": "lea", "collector_number": "161"}
    )
    assert record.printing_id == "abc"
    assert record.set_code == "lea"
