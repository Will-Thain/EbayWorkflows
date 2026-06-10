from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ebay_workflows.operations.image_cache_prune import prune_unreferenced_listing_images


def test_prune_removes_unreferenced_root_files(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    referenced = cache / "keep.jpg"
    orphan = cache / "orphan.jpg"
    referenced.write_bytes(b"ref")
    orphan.write_bytes(b"orph")

    session = MagicMock()
    session.scalars.return_value = [str(referenced.resolve())]

    report = prune_unreferenced_listing_images(session, str(cache), dry_run=False)
    assert report.orphan_files == 1
    assert report.bytes_reclaimed == len(b"orph")
    assert referenced.is_file()
    assert not orphan.is_file()
