from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def _download_bytes(url: str, timeout_ms: int) -> bytes:
    with httpx.Client(timeout=timeout_ms / 1000) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def download_to_cache(url: str, cache_dir: str, timeout_ms: int) -> tuple[str, str]:
    data = _download_bytes(url, timeout_ms)
    content_hash = hashlib.sha256(data).hexdigest()
    ext = Path(url).suffix or ".jpg"
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    output_path = Path(cache_dir) / f"{content_hash}{ext}"
    output_path.write_bytes(data)
    return str(output_path), content_hash

