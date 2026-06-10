"""Map v0.3 ImageAnalysisResult to Phase 5 persistence views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mtg_card_recognition.embeddings.search import EmbeddingMatch
from mtg_card_recognition.pipeline.image_analysis import ImageAnalysisResult
from mtg_card_recognition.zones.regions import CardRegion


@dataclass(slots=True)
class CascadeRegionView:
    """One non-skipped region from a v0.3 listing analysis."""

    region: CardRegion
    region_id: str
    region_path: str
    fields: dict[str, tuple[str, float]]
    zone_evidence: dict[str, Any]
    embedding_matches: list[EmbeddingMatch]


def fields_from_signals(signals: dict[str, Any]) -> dict[str, tuple[str, float]]:
    fields: dict[str, tuple[str, float]] = {}
    name = signals.get("name_ocr")
    if name:
        fields["title"] = (str(name), 0.8)
    bottom = signals.get("bottom_parsed") or {}
    conf = float(bottom.get("ocr_confidence", 0.5))
    if bottom.get("set_code"):
        fields["set_code"] = (str(bottom["set_code"]), conf)
    if bottom.get("collector_number"):
        fields["collector_number"] = (str(bottom["collector_number"]), conf)
    return fields


def embedding_matches_from_signals(signals: dict[str, Any]) -> list[EmbeddingMatch]:
    matches: list[EmbeddingMatch] = []
    for row in signals.get("faiss_top") or []:
        matches.append(
            EmbeddingMatch(
                scryfall_id=str(row.get("printing_id") or row.get("scryfall_id")),
                card_name=None,
                score=float(row.get("score", 0.0)),
            )
        )
    return matches


def zone_evidence_from_signals(signals: dict[str, Any]) -> dict[str, Any]:
    symbol = signals.get("symbol_match")
    payload = dict(signals)
    if symbol and "set_symbol_match" not in payload:
        payload["set_symbol_match"] = symbol
    return payload


def cascade_regions_from_analysis(analysis: ImageAnalysisResult) -> list[CascadeRegionView]:
    """Iterate non-skipped cascade regions with persistence-friendly fields."""
    if analysis.skipped or analysis.cascade is None or analysis.gate is None:
        return []

    views: list[CascadeRegionView] = []
    for index, (region_result, spec, evidence_row) in enumerate(
        zip(
            analysis.cascade.regions,
            analysis.region_specs,
            analysis.cascade.region_evidence,
            strict=False,
        )
    ):
        if region_result.skipped:
            continue
        card_region = (
            analysis.gate.regions[index]
            if index < len(analysis.gate.regions)
            else CardRegion(0, 0, 1, 1, 0.5, spec.region_path)
        )
        signals = evidence_row.get("signals") or region_result.signals.to_dict()
        region_id = str(evidence_row.get("region_id") or spec.region_id or f"region-{index}")
        region_path = card_region.crop_path or spec.region_path
        views.append(
            CascadeRegionView(
                region=card_region,
                region_id=region_id,
                region_path=region_path,
                fields=fields_from_signals(signals),
                zone_evidence=zone_evidence_from_signals(signals),
                embedding_matches=embedding_matches_from_signals(signals),
            )
        )
    return views
