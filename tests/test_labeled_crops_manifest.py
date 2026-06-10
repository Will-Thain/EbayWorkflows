"""Labeled crop fixture manifest checks (consumer repo pointer)."""

from __future__ import annotations

from pathlib import Path


def test_labeled_crops_readme_points_at_sibling_repo() -> None:
    readme = Path("tests/fixtures/labeled_crops/README.md")
    text = readme.read_text(encoding="utf-8")
    assert "mtg-card-recognition/tests/fixtures/labeled_crops" in text
    assert "curate_labeled_crops.py" in text


def test_curate_script_exists() -> None:
    assert Path("scripts/curate_labeled_crops.py").is_file()
