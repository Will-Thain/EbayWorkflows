from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ListingImage


@dataclass(frozen=True)
class ImageCachePruneReport:
    cache_dir: str
    referenced_files: int
    orphan_files: int
    bytes_reclaimed: int
    dry_run: bool


def prune_unreferenced_listing_images(
    session: Session,
    cache_dir: str,
    *,
    dry_run: bool = True,
) -> ImageCachePruneReport:
    """
    Remove hash-named listing download files in the cache root that are not
    referenced by listing_images.local_path. Subdirectories (crops, art, etc.) are untouched.
    """
    root = Path(cache_dir).resolve()
    if not root.is_dir():
        return ImageCachePruneReport(cache_dir=str(root), referenced_files=0, orphan_files=0, bytes_reclaimed=0, dry_run=dry_run)

    referenced: set[Path] = set()
    for local_path in session.scalars(
        select(ListingImage.local_path).where(ListingImage.local_path.is_not(None))
    ):
        if not local_path:
            continue
        referenced.add(Path(local_path).resolve())

    orphan_files = 0
    bytes_reclaimed = 0
    for path in root.iterdir():
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in referenced:
            continue
        orphan_files += 1
        bytes_reclaimed += path.stat().st_size
        if not dry_run:
            path.unlink(missing_ok=True)

    return ImageCachePruneReport(
        cache_dir=str(root),
        referenced_files=len(referenced),
        orphan_files=orphan_files,
        bytes_reclaimed=bytes_reclaimed,
        dry_run=dry_run,
    )
