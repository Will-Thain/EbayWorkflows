from __future__ import annotations

from pathlib import Path


def test_app_qss_contains_key_selectors() -> None:
    styles = Path(__file__).resolve().parents[1] / "src" / "ebay_workflows" / "gui" / "styles"
    for name in ("app.qss", "app_dark.qss"):
        content = (styles / name).read_text(encoding="utf-8")
        assert "QTabWidget#mainTabs" in content
        assert "QFrame#workflowTile" in content
        assert "QLabel#statusChip" in content
