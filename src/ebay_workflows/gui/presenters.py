from __future__ import annotations

from pathlib import Path


def is_safe_cache_path(path: str | None, cache_dir: str) -> bool:
    """True when path resolves inside the configured image cache directory."""
    if not path:
        return False
    try:
        resolved = Path(path).resolve()
        root = Path(cache_dir).resolve()
        return resolved.is_relative_to(root) and resolved.is_file()
    except (OSError, ValueError):
        return False


def truncate_title(title: str, max_len: int = 72) -> str:
    if len(title) <= max_len:
        return title
    return title[: max_len - 1] + "…"
