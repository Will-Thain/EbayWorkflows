"""Reusable themed GUI widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import set_widget_state


class PageHeader(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)

        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("pageSubtitle")
        self._subtitle.setWordWrap(True)
        self._subtitle.setVisible(bool(subtitle))
        layout.addWidget(self._subtitle)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))


class SectionTitle(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("sectionTitle")


class HintLabel(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("hintLabel")
        self.setWordWrap(True)


class StatusChip(QLabel):
    _LABELS = {
        "live": "LIVE",
        "warming": "WARMING",
        "stale": "STALE",
        "paused": "PAUSED",
        "external": "EXTERNAL",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusChip")
        self.set_state("live")

    def set_state(self, state: str) -> None:
        key = state if state in self._LABELS else "live"
        self.setText(self._LABELS.get(key, key.upper()))
        set_widget_state(self, "chipState", key)


class StatCard(QFrame):
    def __init__(
        self,
        title: str,
        *,
        accent: str = "default",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        if accent != "default":
            set_widget_state(self, "statAccent", accent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self._value = QLabel("—")
        self._value.setObjectName("statValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._value)

        caption = QLabel(title)
        caption.setObjectName("statCaption")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(caption)

    def set_value(self, text: str) -> None:
        self._value.setText(text)


class WorkflowTile(QFrame):
    """Launch tile for Workflows → Run now."""

    run_requested = Signal(str)

    def __init__(
        self,
        job_id: str,
        label: str,
        duration_tier: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._job_id = job_id
        self.setObjectName("workflowTile")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(label)
        title.setObjectName("tileTitle")
        title.setWordWrap(True)
        header.addWidget(title, stretch=1)

        badge = QLabel(duration_tier.upper())
        badge.setObjectName("durationBadge")
        set_widget_state(badge, "tier", duration_tier)
        header.addWidget(badge)
        layout.addLayout(header)

        run_btn = QPushButton("Run")
        run_btn.setObjectName("primaryButton")
        run_btn.setToolTip(f"Start {label} ({duration_tier} run)")
        run_btn.clicked.connect(lambda: self.run_requested.emit(self._job_id))
        layout.addWidget(run_btn)
        self._run_btn = run_btn

    def set_active(self, active: bool) -> None:
        set_widget_state(self, "active", active)

    def set_enabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._run_btn.setEnabled(enabled)


class CardFrame(QFrame):
    """Base card with optional cardState for QSS."""

    def __init__(self, object_name: str = "workflowCard", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)

    def set_card_state(self, state: str) -> None:
        if state in ("", "default", "normal"):
            set_widget_state(self, "cardState", "")
        else:
            set_widget_state(self, "cardState", state)
