from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Iterator

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import Settings
from ..services.ingest_helpers import EBAY_BROWSE_MAX_OFFSET

EBAY_OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"
EBAY_API_HOSTS = {
    "production": "https://api.ebay.com",
    "sandbox": "https://api.sandbox.ebay.com",
}


def _api_hosts(settings: Settings) -> tuple[str, str]:
    host = EBAY_API_HOSTS["sandbox" if settings.ebay_use_sandbox else "production"]
    oauth_url = f"{host}/identity/v1/oauth2/token"
    browse_search_url = f"{host}/buy/browse/v1/item_summary/search"
    return oauth_url, browse_search_url


@dataclass
class ListingRecord:
    external_listing_id: str
    title: str
    listing_url: str
    currency: str
    price_amount: float
    shipping_amount: float | None
    condition_text: str | None
    image_urls: list[str]
    raw_payload: dict


class RateLimiter:
    def __init__(self, requests_per_minute: int):
        self._interval = 60.0 / requests_per_minute
        self._next_allowed_at = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        if now < self._next_allowed_at:
            time.sleep(self._next_allowed_at - now)
        self._next_allowed_at = time.monotonic() + self._interval


@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    data: dict | None = None,
    params: dict | None = None,
) -> httpx.Response:
    response = client.request(method=method, url=url, headers=headers, data=data, params=params)
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", "1"))
        time.sleep(max(retry_after, 1))
        response.raise_for_status()
    response.raise_for_status()
    return response


def _oauth_token(settings: Settings, client: httpx.Client, limiter: RateLimiter) -> str:
    client_id = settings.resolved_ebay_client_id
    client_secret = settings.resolved_ebay_client_secret
    if not client_id or not client_secret:
        raise ValueError("Missing eBay client credentials for the active environment.")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {basic}",
    }
    oauth_url, _ = _api_hosts(settings)
    data = {
        "grant_type": "client_credentials",
        "scope": EBAY_OAUTH_SCOPE,
    }
    limiter.wait()
    response = client.post(oauth_url, headers=headers, data=data)
    if response.status_code >= 400:
        detail = response.text[:300]
        env_label = "sandbox" if settings.ebay_use_sandbox else "production"
        raise ValueError(
            f"eBay OAuth failed ({response.status_code}, {env_label}): {detail}. "
            "Verify production (EBAY_CLIENT_ID/EBAY_CLIENT_SECRET) or sandbox "
            "(EBAY_SANDBOX_CLIENT_ID/EBAY_SANDBOX_CLIENT_SECRET) credentials match EBAY_USE_SANDBOX "
            "(App ID + Client Secret from Developer Portal keys, not Cert ID)."
        )
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise ValueError("eBay OAuth response did not include access_token.")
    return token


def _extract_record(item: dict) -> ListingRecord:
    shipping_options = item.get("shippingOptions") or []
    shipping_cost = None
    if shipping_options:
        first_shipping = shipping_options[0].get("shippingCost") or {}
        shipping_cost = float(first_shipping["value"]) if first_shipping.get("value") is not None else None

    image_urls: list[str] = []
    image = item.get("image") or {}
    if image.get("imageUrl"):
        image_urls.append(image["imageUrl"])
    for extra in item.get("additionalImages") or []:
        if extra.get("imageUrl"):
            image_urls.append(extra["imageUrl"])

    price = (item.get("price") or {}).get("value")
    currency = (item.get("price") or {}).get("currency", "GBP")
    if price is None:
        price = 0

    return ListingRecord(
        external_listing_id=item.get("itemId", ""),
        title=item.get("title", ""),
        listing_url=item.get("itemWebUrl", ""),
        currency=currency,
        price_amount=float(price),
        shipping_amount=shipping_cost,
        condition_text=item.get("condition"),
        image_urls=image_urls,
        raw_payload=item,
    )


def verify_ebay_credentials(settings: Settings) -> str:
    """Obtain an OAuth token to verify client ID/secret and environment selection."""
    if not settings.enable_ebay_api:
        raise ValueError("ENABLE_EBAY_API is false.")
    if settings.ebay_requests_per_minute is None:
        raise ValueError("EBAY_REQUESTS_PER_MINUTE is required when eBay API is enabled.")
    limiter = RateLimiter(settings.ebay_requests_per_minute)
    with httpx.Client(timeout=30) as client:
        return _oauth_token(settings, client, limiter)


def iter_listing_pages(
    settings: Settings,
    query: str,
    max_pages: int,
) -> Iterator[list[ListingRecord]]:
    """Yield one page of listing records at a time (memory-safe for large ingests)."""
    if not settings.enable_ebay_api:
        return
    if settings.ebay_requests_per_minute is None:
        raise ValueError("EBAY_REQUESTS_PER_MINUTE is required when eBay API is enabled.")

    limiter = RateLimiter(settings.ebay_requests_per_minute)
    page_size = settings.ebay_page_size
    offset = 0

    _, browse_search_url = _api_hosts(settings)

    with httpx.Client(timeout=30) as client:
        token = _oauth_token(settings, client, limiter)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": settings.ebay_marketplace_id,
        }

        for _ in range(max_pages):
            if offset >= EBAY_BROWSE_MAX_OFFSET:
                break

            limiter.wait()
            response = _request_with_retry(
                client,
                "GET",
                browse_search_url,
                headers=headers,
                params={
                    "q": query,
                    "limit": page_size,
                    "offset": offset,
                },
            )
            payload = response.json()
            items = payload.get("itemSummaries", [])
            if not items:
                break

            page_records: list[ListingRecord] = []
            for item in items:
                record = _extract_record(item)
                if not record.external_listing_id or not record.title or not record.listing_url:
                    continue
                page_records.append(record)

            if page_records:
                yield page_records

            total = payload.get("total")
            offset += page_size
            if total is not None and offset >= int(total):
                break


def fetch_listings(settings: Settings, query: str, max_pages: int) -> list[ListingRecord]:
    records: list[ListingRecord] = []
    for page in iter_listing_pages(settings, query, max_pages):
        records.extend(page)
    return records

