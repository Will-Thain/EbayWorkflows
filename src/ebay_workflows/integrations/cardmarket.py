from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def load_cardmarket_bulk_rows(path: str) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Cardmarket bulk file not found: {file_path}")
    rows: list[dict[str, Any]] = []
    with file_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(row)
    if not rows:
        raise ValueError("Cardmarket bulk file is empty.")
    return rows

