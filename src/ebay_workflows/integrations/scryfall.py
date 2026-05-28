from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import Settings


@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _download_bulk(url: str) -> list[dict[str, Any]]:
    with httpx.Client(timeout=90) as client:
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()
        # Scryfall bulk-data endpoint returns metadata with download_uri.
        if isinstance(payload, dict):
            download_uri = payload.get("download_uri")
            if not download_uri:
                raise ValueError("Scryfall bulk metadata missing download_uri.")
            bulk_response = client.get(download_uri)
            bulk_response.raise_for_status()
            cards_payload = bulk_response.json()
            if not isinstance(cards_payload, list):
                raise ValueError("Scryfall downloaded bulk payload is not a list.")
            return cards_payload
        if isinstance(payload, list):
            return payload
    raise ValueError("Scryfall bulk payload is not a list or metadata object.")


def sync_scryfall_bulk(settings: Settings) -> list[dict[str, Any]]:
    cards = _download_bulk(settings.scryfall_bulk_uri)
    out_path = Path(settings.scryfall_bulk_cache_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cards), encoding="utf-8")
    return cards

