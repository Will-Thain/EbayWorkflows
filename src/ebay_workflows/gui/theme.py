"""Central GUI theme: QSS load, layout helpers, dynamic property updates."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QTableView, QVBoxLayout, QWidget

TAB_MARGINS = (16, 16, 16, 16)
TAB_SPACING = 12


def _styles_path() -> Path:
    return Path(__file__).resolve().parent / "styles" / "app.qss"


def load_stylesheet() -> str:
    path = _styles_path()
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def apply_app_theme(app: QApplication) -> None:
    """Apply Fusion + global QSS."""
    app.setStyle("Fusion")
    qss = load_stylesheet()
    if qss:
        app.setStyleSheet(qss)
    default_font = QFont("Segoe UI", 10)
    if not default_font.exactMatch():
        default_font = QFont()
        default_font.setPointSize(10)
    app.setFont(default_font)


def apply_tab_layout(widget: QWidget) -> QVBoxLayout:
    """Standard margins and spacing for tab roots."""
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(*TAB_MARGINS)
    layout.setSpacing(TAB_SPACING)
    return layout


def set_widget_state(widget: QWidget, name: str, value: str | bool) -> None:
    """Update a QSS dynamic property and re-polish."""
    widget.setProperty(name, value)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def configure_data_table(table: QTableView) -> None:
    """Shared table appearance."""
    table.setObjectName("dataTable")
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setStretchLastSection(True)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
