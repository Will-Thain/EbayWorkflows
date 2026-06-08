from __future__ import annotations

from pathlib import Path


def test_app_qss_contains_key_selectors() -> None:
    qss_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "ebay_workflows"
        / "gui"
        / "styles"
        / "app.qss"
    )
    content = qss_path.read_text(encoding="utf-8")
    assert "QTabWidget#mainTabs" in content
    assert "QFrame#workflowTile" in content
    assert "QLabel#statusChip" in content
