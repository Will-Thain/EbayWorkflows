from __future__ import annotations

from pathlib import Path

import pytest

from ebay_workflows.services.card_align import normalize_card_image
from ebay_workflows.services.card_zones import (
    DFC_FRONT_ZONES,
    OLD_FRAME_MTG_ZONES,
    STANDARD_MTG_ZONES,
    detect_frame_layout,
    prepare_card_for_zones,
    zones_for_layout,
)
from ebay_workflows.services.mana_cost import detect_mana_pips
from ebay_workflows.services.set_symbol_match import match_set_symbol
from ebay_workflows.config import Settings


def _settings(**overrides: object) -> Settings:
    base = {
        "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
        "SCRYFALL_BULK_URI": "https://example.com/bulk",
        "CARDMARKET_BULK_FILE_PATH": "./data/cardmarket/prices.csv",
        "IMAGE_CACHE_DIR": "./.cache/images",
        "FAISS_INDEX_PATH": "./.cache/faiss/index.bin",
        "GLOBAL_REQUESTS_PER_MINUTE_CAP": 90,
    }
    base.update(overrides)
    return Settings(**base)


def test_detect_frame_layout_dfc_by_aspect() -> None:
    cv2 = pytest.importorskip("cv2")
    import numpy as np  # type: ignore[import-not-found]

    tall = np.full((900, 500, 3), 240, dtype=np.uint8)
    cv2.rectangle(tall, (20, 20), (479, 879), (0, 0, 0), 2)
    assert detect_frame_layout(tall) == "dfc_front"


def test_zones_for_layout_returns_templates() -> None:
    assert "set_symbol" in zones_for_layout("modern")
    assert zones_for_layout("old") is OLD_FRAME_MTG_ZONES
    assert zones_for_layout("dfc_front") is DFC_FRONT_ZONES
    assert zones_for_layout("modern") is STANDARD_MTG_ZONES


def test_normalize_card_image_warps_rectangle(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    import numpy as np  # type: ignore[import-not-found]

    canvas = np.zeros((400, 300, 3), dtype=np.uint8)
    pts = np.array([[40, 30], [260, 50], [250, 370], [30, 350]], dtype=np.int32)
    cv2.fillPoly(canvas, [pts], (200, 200, 200))
    src = tmp_path / "skewed.jpg"
    cv2.imwrite(str(src), canvas)
    out = tmp_path / "aligned.jpg"
    path, conf = normalize_card_image(str(src), str(out))
    assert path is not None
    assert conf > 0
    assert out.is_file()


def test_prepare_card_for_zones_creates_symbol_and_mana(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    import numpy as np  # type: ignore[import-not-found]

    card = np.full((680, 488, 3), 255, dtype=np.uint8)
    cv2.rectangle(card, (0, 0), (487, 679), (0, 0, 0), 2)
    cv2.putText(card, "Lightning Bolt", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    cv2.circle(card, (430, 50), 18, (0, 0, 255), -1)
    cv2.circle(card, (400, 380), 16, (120, 120, 120), -1)
    cv2.putText(card, "233/297 MKM", (20, 650), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    card_path = tmp_path / "card.jpg"
    cv2.imwrite(str(card_path), card)

    settings = _settings()
    crops, meta = prepare_card_for_zones(str(card_path), str(tmp_path / "zones"), settings)
    assert crops.name_path
    assert crops.art_path
    assert crops.set_symbol_path
    assert crops.mana_cost_path
    assert meta.get("frame_layout") in {"modern", "old", "dfc_front"}


def test_soft_resize_card_image_produces_canonical(tmp_path) -> None:
    cv2 = pytest.importorskip("cv2")
    import numpy as np  # type: ignore[import-not-found]

    canvas = np.full((300, 400, 3), 180, dtype=np.uint8)
    src = tmp_path / "wide.jpg"
    out = tmp_path / "soft.jpg"
    cv2.imwrite(str(src), canvas)
    from ebay_workflows.services.card_align import CANONICAL_CARD_HEIGHT, CANONICAL_CARD_WIDTH, soft_resize_card_image

    path, conf = soft_resize_card_image(str(src), str(out))
    assert path is not None
    assert conf > 0
    image = cv2.imread(str(out))
    assert image is not None
    assert image.shape[1] == CANONICAL_CARD_WIDTH
    assert image.shape[0] == CANONICAL_CARD_HEIGHT


def test_match_set_symbol_with_hints(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    import numpy as np  # type: ignore[import-not-found]

    cache_root = tmp_path / "cache"
    template_dir = cache_root / "set_symbol_templates"
    template_dir.mkdir(parents=True)
    symbol = np.full((48, 48), 180, dtype=np.uint8)
    cv2.circle(symbol, (24, 24), 16, 90, -1)
    cv2.imwrite(str(template_dir / "mkm.png"), symbol)

    query = symbol.copy()
    query_path = tmp_path / "query.jpg"
    cv2.imwrite(str(query_path), query)
    settings = _settings(IMAGE_CACHE_DIR=str(cache_root))

    code, score = match_set_symbol(str(query_path), settings, min_score=0.4, set_code_hints=["MKM"])
    assert code == "MKM"
    assert score >= 0.4


def test_detect_mana_pips_finds_red_blob(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    import numpy as np  # type: ignore[import-not-found]

    strip = np.full((60, 180, 3), 255, dtype=np.uint8)
    cv2.circle(strip, (40, 30), 16, (0, 0, 255), -1)
    path = tmp_path / "mana.jpg"
    cv2.imwrite(str(path), strip)
    mana = detect_mana_pips(str(path))
    assert "R" in mana.colors
