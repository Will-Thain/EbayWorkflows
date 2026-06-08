from __future__ import annotations

from ebay_workflows.services.progress_report import (
    ProgressSnapshot,
    format_progress_label,
    parse_progress_line,
)


def test_parse_standard_progress_line() -> None:
    snap = parse_progress_line("ebay-workflows-progress 42/966 listings")
    assert snap == ProgressSnapshot(current=42, total=966, unit="listings")
    assert snap.percent == 4


def test_parse_legacy_phase_line() -> None:
    snap = parse_progress_line("Phase 5 image analysis: 10/100")
    assert snap == ProgressSnapshot(current=10, total=100, unit="items")


def test_format_progress_label() -> None:
    text = format_progress_label(ProgressSnapshot(5, 20, "images"))
    assert "5 / 20" in text
    assert "25%" in text
