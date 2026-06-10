from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import Settings
from ..exceptions import RateLimitError, TransientIntegrationError
from ..operations.rate_limit import wait_global_http
from .http_errors import raise_for_http_response

SCRYFALL_PROVIDER = "Scryfall"


@retry(
    retry=retry_if_exception_type(
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            RateLimitError,
            TransientIntegrationError,
        )
    ),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _download_bulk(url: str, *, requests_per_minute: int) -> list[dict[str, Any]]:
    with httpx.Client(timeout=90) as client:
        wait_global_http(requests_per_minute)
        response = client.get(url)
        if response.status_code == 429:
            raise RateLimitError(f"{SCRYFALL_PROVIDER} HTTP 429: rate limited")
        raise_for_http_response(response, provider=SCRYFALL_PROVIDER)
        payload = response.json()
        # Scryfall bulk-data endpoint returns metadata with download_uri.
        if isinstance(payload, dict):
            download_uri = payload.get("download_uri")
            if not download_uri:
                raise ValueError("Scryfall bulk metadata missing download_uri.")
            wait_global_http(requests_per_minute)
            bulk_response = client.get(download_uri)
            if bulk_response.status_code == 429:
                raise RateLimitError(f"{SCRYFALL_PROVIDER} HTTP 429: rate limited")
            raise_for_http_response(bulk_response, provider=SCRYFALL_PROVIDER)
            cards_payload = bulk_response.json()
            if not isinstance(cards_payload, list):
                raise ValueError("Scryfall downloaded bulk payload is not a list.")
            return cards_payload
        if isinstance(payload, list):
            return payload
    raise ValueError("Scryfall bulk payload is not a list or metadata object.")


def sync_scryfall_bulk(settings: Settings) -> list[dict[str, Any]]:
    rpm = settings.global_requests_per_minute_cap
    cards = _download_bulk(settings.scryfall_bulk_uri, requests_per_minute=rpm)
    out_path = Path(settings.scryfall_bulk_cache_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cards), encoding="utf-8")
    return cards

