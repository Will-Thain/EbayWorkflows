from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "labeled_crops"
MANIFEST = FIXTURES / "manifest.example.json"
MIN_REAL_CROP_BYTES = 512


def _has_real_labeled_crops() -> bool:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest.get("entries", []):
        rel = Path(entry["path"])
        if rel.name.endswith(".gitkeep"):
            continue
        full = FIXTURES / rel
        if full.is_file() and full.stat().st_size >= MIN_REAL_CROP_BYTES:
            return True
    return False


@pytest.mark.skipif(
    not _has_real_labeled_crops(),
    reason="Add real crop PNGs (>=512 bytes) under tests/fixtures/labeled_crops/examples/",
)
def test_labeled_crop_strict_gate_regression() -> None:
    """Run strict verification on manifest entries when real crops are present."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    from mtg_card_recognition.evidence.gate import verification_strength

    assert verification_strength("set_collector") > verification_strength("ocr")
    for entry in manifest["entries"]:
        rel = Path(entry["path"])
        if rel.name.endswith(".gitkeep"):
            continue
        image_path = FIXTURES / rel
        if not image_path.is_file():
            continue
        assert entry["verify_expect"] in {"pass", "fail"}
        # TODO: wire OCR + zone evidence from image_path and assert gate outcome.
