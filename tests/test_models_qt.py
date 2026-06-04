from __future__ import annotations

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt  # noqa: E402

from ebay_workflows.gui.models_qt import RankedListTableModel  # noqa: E402
from ebay_workflows.services.ranked_export import RankedListingRow


def _sample_row(**kwargs) -> RankedListingRow:
    defaults = {
        "rank": 1,
        "listing_id": "id-1",
        "title": "Test listing",
        "listing_url": "https://example.com",
        "currency": "GBP",
        "price_amount": 9.99,
        "shipping_amount": 1.0,
        "ev_raw": 5.0,
        "ev_adjusted": 4.0,
        "confidence_score": 0.5,
        "risk_score": 0.5,
        "rank_value": 4.0,
        "scoring_version": "v2_hybrid",
        "top_card_name": "Bolt",
        "top_card_match_score": 0.9,
        "is_favorited": True,
    }
    defaults.update(kwargs)
    return RankedListingRow(**defaults)


def test_ranked_table_model_display() -> None:
    model = RankedListTableModel()
    model.set_rows([_sample_row()])

    assert model.rowCount() == 1
    assert model.columnCount() == 7
    assert model.data(model.index(0, 5)) == "★"
    assert model.data(model.index(0, 0), Qt.ItemDataRole.UserRole) == "id-1"
