from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


from .rate_limit import wait_global_http


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def _download_bytes(url: str, timeout_ms: int, *, global_requests_per_minute: int | None = None) -> bytes:
    if global_requests_per_minute:
        wait_global_http(global_requests_per_minute)
    with httpx.Client(timeout=timeout_ms / 1000) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def download_to_cache(
    url: str,
    cache_dir: str,
    timeout_ms: int,
    *,
    global_requests_per_minute: int | None = None,
) -> tuple[str, str]:
    data = _download_bytes(url, timeout_ms, global_requests_per_minute=global_requests_per_minute)
    content_hash = hashlib.sha256(data).hexdigest()
    ext = Path(url).suffix or ".jpg"
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    output_path = Path(cache_dir) / f"{content_hash}{ext}"
    output_path.write_bytes(data)
    return str(output_path), content_hash


def download_many_to_cache(
    urls: list[str],
    cache_dir: str,
    timeout_ms: int,
    *,
    max_workers: int = 8,
    global_requests_per_minute: int | None = None,
) -> dict[str, tuple[str, str] | Exception]:
    """Download many image URLs in parallel; returns url -> (path, hash) or error."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not urls:
        return {}

    unique_urls = list(dict.fromkeys(urls))
    workers = max(1, min(max_workers, len(unique_urls)))
    results: dict[str, tuple[str, str] | Exception] = {}

    def _one(url: str) -> tuple[str, tuple[str, str] | Exception]:
        try:
            return url, download_to_cache(
                url, cache_dir, timeout_ms, global_requests_per_minute=global_requests_per_minute
            )
        except Exception as exc:  # noqa: BLE001
            return url, exc

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_one, url) for url in unique_urls]
        for future in as_completed(futures):
            url, outcome = future.result()
            results[url] = outcome
    return results

