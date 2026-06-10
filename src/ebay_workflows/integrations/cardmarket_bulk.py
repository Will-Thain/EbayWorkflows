from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..exceptions import RateLimitError, TransientIntegrationError
from ..operations.rate_limit import wait_global_http
from .http_errors import raise_for_http_response

CARDMARKET_PROVIDER = "Cardmarket"
CARDMARKET_PRICE_GUIDE_URL = (
    "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_1.json"
)
CARDMARKET_PRODUCTS_SINGLES_URL = (
    "https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_1.json"
)

CSV_COLUMNS = (
    "scryfall_id",
    "name",
    "price_eur",
    "currency",
    "price_type",
    "condition",
    "language",
    "price_timestamp",
)

_PRICE_FIELDS = {
    "trend": "trend",
    "low": "low",
    "avg": "avg",
    "avg7": "avg7",
    "avg30": "avg30",
    "low-foil": "low-foil",
    "trend-foil": "trend-foil",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
def _download_json(
    client: httpx.Client,
    url: str,
    dest: Path,
    *,
    requests_per_minute: int,
) -> None:
    wait_global_http(requests_per_minute)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url, follow_redirects=True) as response:
        if response.status_code == 429:
            raise RateLimitError(f"{CARDMARKET_PROVIDER} HTTP 429: rate limited")
        raise_for_http_response(response, provider=CARDMARKET_PROVIDER)
        dest.write_bytes(response.read())


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_and_build_singles_csv(
    output_csv: str | Path,
    *,
    cache_dir: str | Path = "./data/cardmarket",
    price_field: str = "trend",
    force_download: bool = False,
    timeout_seconds: float = 300.0,
    requests_per_minute: int = 30,
) -> dict[str, Any]:
    """
    Download official Cardmarket MTG singles catalog + price guide (JSON) and
    write a normalized CSV for sync-cardmarket.
    """
    if price_field not in _PRICE_FIELDS:
        raise ValueError(f"Unsupported price_field '{price_field}'. Choose from: {sorted(_PRICE_FIELDS)}")

    output_path = Path(output_csv)
    cache_path = Path(cache_dir)
    products_path = cache_path / "products_singles_1.json"
    price_guide_path = cache_path / "price_guide_1.json"
    meta_path = cache_path / "bulk_metadata.json"

    with httpx.Client(timeout=timeout_seconds) as client:
        if force_download or not products_path.is_file():
            _download_json(
                client,
                CARDMARKET_PRODUCTS_SINGLES_URL,
                products_path,
                requests_per_minute=requests_per_minute,
            )
        if force_download or not price_guide_path.is_file():
            _download_json(
                client,
                CARDMARKET_PRICE_GUIDE_URL,
                price_guide_path,
                requests_per_minute=requests_per_minute,
            )

    products_payload = json.loads(products_path.read_text(encoding="utf-8"))
    price_payload = json.loads(price_guide_path.read_text(encoding="utf-8"))

    product_name_by_id: dict[int, str] = {}
    for product in products_payload.get("products", []):
        product_id = product.get("idProduct")
        name = (product.get("name") or "").strip()
        if product_id is None or not name:
            continue
        product_name_by_id[int(product_id)] = name

    guide_key = _PRICE_FIELDS[price_field]
    exported_at = price_payload.get("createdAt") or _now_iso()
    rows_written = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for guide in price_payload.get("priceGuides", []):
            product_id = guide.get("idProduct")
            if product_id is None:
                continue
            name = product_name_by_id.get(int(product_id))
            if not name:
                continue
            price_value = guide.get(guide_key)
            if price_value is None:
                continue
            try:
                price = float(price_value)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            writer.writerow(
                {
                    "scryfall_id": "",
                    "name": name,
                    "price_eur": f"{price:.2f}",
                    "currency": "EUR",
                    "price_type": price_field,
                    "condition": "EX",
                    "language": "EN",
                    "price_timestamp": exported_at,
                }
            )
            rows_written += 1

    metadata = {
        "source": "cardmarket_s3_export",
        "products_url": CARDMARKET_PRODUCTS_SINGLES_URL,
        "price_guide_url": CARDMARKET_PRICE_GUIDE_URL,
        "products_file": str(products_path),
        "price_guide_file": str(price_guide_path),
        "output_csv": str(output_path),
        "products_sha256": _file_sha256(products_path),
        "price_guide_sha256": _file_sha256(price_guide_path),
        "price_field": price_field,
        "rows_written": rows_written,
        "products_count": len(product_name_by_id),
        "downloaded_at": _now_iso(),
        "export_created_at": exported_at,
    }
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata
