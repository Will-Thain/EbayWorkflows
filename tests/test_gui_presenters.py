from __future__ import annotations

from pathlib import Path

from ebay_workflows.gui.presenters import is_safe_cache_path, truncate_title


def test_truncate_title() -> None:
    assert truncate_title("short") == "short"
    long = "x" * 100
    assert len(truncate_title(long)) == 72
    assert truncate_title(long).endswith("…")


def test_is_safe_cache_path(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    inside = cache / "img.jpg"
    inside.write_bytes(b"fake")
    outside = tmp_path / "other.jpg"
    outside.write_bytes(b"fake")

    assert is_safe_cache_path(str(inside), str(cache))
    assert not is_safe_cache_path(str(outside), str(cache))
    assert not is_safe_cache_path(None, str(cache))
