from __future__ import annotations

import pytest

from ebay_workflows.exceptions import PermanentIntegrationError
from ebay_workflows.integrations.cardmarket_bulk import _download_json


def test_cardmarket_download_raises_typed_error_on_404(tmp_path) -> None:
    import httpx

    dest = tmp_path / "missing.json"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(PermanentIntegrationError, match="Cardmarket HTTP 404"):
            _download_json(
                client,
                "https://downloads.s3.cardmarket.com/productCatalog/does-not-exist.json",
                dest,
                requests_per_minute=120,
            )
    assert not dest.exists()
