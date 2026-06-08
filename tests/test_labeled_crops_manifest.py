from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "labeled_crops"
SCHEMA = json.loads((FIXTURES / "manifest.schema.json").read_text(encoding="utf-8"))
REQUIRED_ENTRY_KEYS = {"id", "path", "verify_expect"}
ALLOWED_ENTRY_KEYS = REQUIRED_ENTRY_KEYS | {
    "expected_set",
    "expected_collector",
    "expected_name",
    "notes",
}


def _validate_manifest(manifest: dict) -> None:
    assert manifest.get("version", 0) >= 1
    entries = manifest.get("entries")
    assert isinstance(entries, list)
    for entry in entries:
        assert isinstance(entry, dict)
        assert REQUIRED_ENTRY_KEYS <= set(entry.keys())
        assert set(entry.keys()) <= ALLOWED_ENTRY_KEYS
        assert entry["verify_expect"] in {"pass", "fail"}


def test_example_manifest_matches_schema_shape() -> None:
    manifest = json.loads((FIXTURES / "manifest.example.json").read_text(encoding="utf-8"))
    _validate_manifest(manifest)
    assert manifest["version"] == 1
    assert len(manifest["entries"]) >= 1


def test_manifest_paths_are_relative_under_fixtures() -> None:
    manifest = json.loads((FIXTURES / "manifest.example.json").read_text(encoding="utf-8"))
    for entry in manifest["entries"]:
        rel = Path(entry["path"])
        assert not rel.is_absolute()
        assert ".." not in rel.parts
