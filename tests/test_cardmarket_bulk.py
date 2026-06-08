from __future__ import annotations

import json
from pathlib import Path

from ebay_workflows.integrations.cardmarket_bulk import download_and_build_singles_csv


def test_build_singles_csv_from_cached_json(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "products_singles_1.json").write_text(
        json.dumps(
            {
                "products": [
                    {"idProduct": 1, "name": "Lightning Bolt"},
                    {"idProduct": 2, "name": "Sol Ring"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (cache / "price_guide_1.json").write_text(
        json.dumps(
            {
                "createdAt": "2026-06-03T12:00:00Z",
                "priceGuides": [
                    {"idProduct": 1, "trend": 2.5, "low": 1.0},
                    {"idProduct": 2, "trend": 10.0, "low": 8.0},
                    {"idProduct": 99, "trend": 1.0},
                ],
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "prices.csv"
    meta = download_and_build_singles_csv(
        out,
        cache_dir=cache,
        price_field="trend",
        force_download=False,
    )

    assert meta["rows_written"] == 2
    text = out.read_text(encoding="utf-8")
    assert "Lightning Bolt" in text
    assert "Sol Ring" in text
