"""Central GUI theme: QSS load, layout helpers, dynamic property updates."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QTableView, QVBoxLayout, QWidget

TAB_MARGINS = (16, 16, 16, 16)
TAB_SPACING = 12
_SETTINGS_ORG = "EbayWorkflows"
_SETTINGS_APP = "GUI"
_DARK_MODE_KEY = "dark_mode"


def _styles_dir() -> Path:
    return Path(__file__).resolve().parent / "styles"


def load_stylesheet(*, dark: bool = False) -> str:
    name = "app_dark.qss" if dark else "app.qss"
    path = _styles_dir() / name
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def is_dark_mode_enabled() -> bool:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    return bool(settings.value(_DARK_MODE_KEY, False, type=bool))


def set_dark_mode_enabled(enabled: bool) -> None:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue(_DARK_MODE_KEY, enabled)


def apply_app_theme(app: QApplication, *, dark: bool | None = None) -> None:
    """Apply Fusion + global QSS (light or dark)."""
    app.setStyle("Fusion")
    use_dark = is_dark_mode_enabled() if dark is None else dark
    qss = load_stylesheet(dark=use_dark)
    if qss:
        app.setStyleSheet(qss)
    default_font = QFont("Segoe UI", 10)
    if not default_font.exactMatch():
        default_font = QFont()
        default_font.setPointSize(10)
    app.setFont(default_font)


def toggle_dark_mode(app: QApplication) -> bool:
    """Flip theme; returns new dark-mode state."""
    enabled = not is_dark_mode_enabled()
    set_dark_mode_enabled(enabled)
    apply_app_theme(app, dark=enabled)
    return enabled


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
