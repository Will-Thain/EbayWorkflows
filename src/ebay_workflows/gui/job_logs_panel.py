from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings
from ..operations.workflow_logs import list_workflow_log_files
from ..models_qt import GenericTableModel
from .theme import configure_data_table
from .widgets import HintLabel, SectionTitle


class JobLogsPanel(QWidget):
    """Browse detached/scheduled workflow logs under WORKFLOW_LOG_DIR."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._log_paths: list[str] = []
        self._rows: list[tuple] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(SectionTitle("Workflow logs"))
        layout.addWidget(
            HintLabel(
                "Scheduled and headless CLI runs write logs here. "
                "GUI-started jobs stream to the Run now log panel instead."
            )
        )

        toolbar = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(refresh_btn)
        open_dir_btn = QPushButton("Open logs folder")
        open_dir_btn.setObjectName("secondaryButton")
        open_dir_btn.clicked.connect(self._open_log_dir)
        toolbar.addWidget(open_dir_btn)
        open_file_btn = QPushButton("Open selected log")
        open_file_btn.setObjectName("primaryButton")
        open_file_btn.clicked.connect(self._open_selected)
        toolbar.addWidget(open_file_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._table = QTableView()
        configure_data_table(self._table)
        self._model = GenericTableModel(self)
        self._table.setModel(self._model)
        layout.addWidget(self._table, stretch=1)
        self.refresh()

    def refresh(self) -> None:
        logs = list_workflow_log_files(self._settings.workflow_log_dir)
        headers = ["Modified (UTC)", "Job", "Size", "File"]
        rows = [
            (
                log.modified_at.strftime("%Y-%m-%d %H:%M:%S"),
                log.job_id or "—",
                f"{log.size_bytes:,} B",
                log.path.name,
            )
            for log in logs
        ]
        self._log_paths = [str(log.path) for log in logs]
        self._model.set_data(headers, rows)

    def _open_log_dir(self) -> None:
        path = Path(self._settings.workflow_log_dir)
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _open_selected(self) -> None:
        index = self._table.currentIndex()
        if not index.isValid() or index.row() >= len(self._log_paths):
            QMessageBox.information(self, "Workflow logs", "Select a log file first.")
            return
        log_path = Path(self._log_paths[index.row()])
        if not log_path.is_file():
            QMessageBox.warning(self, "Workflow logs", f"Log file not found:\n{log_path}")
            self.refresh()
            return
        if sys.platform == "win32":
            import os

            os.startfile(log_path)  # noqa: S606
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path.resolve())))
