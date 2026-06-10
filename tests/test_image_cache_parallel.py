from __future__ import annotations

from unittest.mock import patch

from ebay_workflows.operations.image_cache import download_many_to_cache


def test_download_many_to_cache_deduplicates_urls() -> None:
    urls = ["https://example.com/a.jpg", "https://example.com/a.jpg", "https://example.com/b.jpg"]

    def fake_download(url: str, cache_dir: str, timeout_ms: int, **kwargs: object) -> tuple[str, str]:
        return f"/tmp/{url.split('/')[-1]}", f"hash-{url}"

    with patch("ebay_workflows.operations.image_cache.download_to_cache", side_effect=fake_download):
        results = download_many_to_cache(urls, "/cache", 1000, max_workers=2)

    assert len(results) == 2
    assert "https://example.com/a.jpg" in results
    assert "https://example.com/b.jpg" in results


def test_download_many_to_cache_records_failures() -> None:
    def fake_download(url: str, cache_dir: str, timeout_ms: int, **kwargs: object) -> tuple[str, str]:
        if url.endswith("bad.jpg"):
            raise RuntimeError("network down")
        return f"/tmp/{url.split('/')[-1]}", "ok"

    with patch("ebay_workflows.operations.image_cache.download_to_cache", side_effect=fake_download):
        results = download_many_to_cache(
            ["https://example.com/good.jpg", "https://example.com/bad.jpg"],
            "/cache",
            1000,
            max_workers=2,
        )

    assert results["https://example.com/good.jpg"] == ("/tmp/good.jpg", "ok")
    assert isinstance(results["https://example.com/bad.jpg"], RuntimeError)
