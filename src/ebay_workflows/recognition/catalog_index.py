"""Build recognition catalog indexes from EbayWorkflows Scryfall rows."""

from __future__ import annotations

from typing import Any

from mtg_card_recognition.catalog.lookup import CatalogIndex
from mtg_card_recognition.catalog.printing import PrintingRecord
from mtg_card_recognition.ir.sidecar_index import SidecarIndex


def catalog_from_scryfall_rows(rows: list[Any]) -> CatalogIndex:
    records = [PrintingRecord.from_mapping(row) for row in rows]
    return CatalogIndex.from_records(records)


def sidecar_from_catalog(catalog: CatalogIndex) -> SidecarIndex:
    return SidecarIndex.build(catalog.records)
