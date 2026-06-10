from __future__ import annotations

import uuid

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings
from ..operations.stale_workflows import (
    clear_stale_workflow_steps,
    delete_workflow_steps,
    list_running_workflow_views,
)
from .job_runner import JobRunner
from ..models_qt import GenericTableModel
from .poll_errors import GuiPollErrorReporter, handle_poll_error
from .theme import configure_data_table
from .widgets import HintLabel


class StaleWorkflowsPanel(QWidget):
    """Identify and clear workflow_steps stuck in status=running."""

    changed = Signal()

    def __init__(
        self,
        settings: Settings,
        session_factory,
        job_runner: JobRunner,
        poll_reporter: GuiPollErrorReporter | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._session_factory = session_factory
        self._runner = job_runner
        self._poll_reporter = poll_reporter
        self._views: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(
            HintLabel(
                "Rows with status running in the database. "
                "Stale rows have no recent progress and can be cleared to unblock new jobs."
            )
        )

        self._table = QTableView()
        self._model = GenericTableModel(self)
        self._table.setModel(self._model)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        configure_data_table(self._table)
        layout.addWidget(self._table, stretch=1)

        actions = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("secondaryButton")
        self._refresh_btn.clicked.connect(self.refresh)
        actions.addWidget(self._refresh_btn)

        self._clear_selected_btn = QPushButton("Clear selected stale")
        self._clear_selected_btn.setObjectName("primaryButton")
        self._clear_selected_btn.setToolTip("Mark the selected stale step as failed")
        self._clear_selected_btn.clicked.connect(self._clear_selected)
        self._clear_selected_btn.setEnabled(False)
        actions.addWidget(self._clear_selected_btn)

        self._clear_all_btn = QPushButton("Clear all stale")
        self._clear_all_btn.setObjectName("primaryButton")
        self._clear_all_btn.setToolTip("Mark every stale running step as failed")
        self._clear_all_btn.clicked.connect(self._clear_all_stale)
        self._clear_all_btn.setEnabled(False)
        actions.addWidget(self._clear_all_btn)

        self._delete_btn = QPushButton("Delete selected rows")
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.setToolTip("Remove selected step rows from the database")
        self._delete_btn.clicked.connect(self._delete_selected)
        self._delete_btn.setEnabled(False)
        actions.addWidget(self._delete_btn)

        actions.addStretch()
        layout.addLayout(actions)

        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        self._poll = QTimer(self)
        self._poll.setInterval(5000)
        self._poll.timeout.connect(self.refresh)
        self._poll.start()

        self.refresh()

    def refresh(self) -> None:
        try:
            with self._session_factory() as session:
                self._views = list_running_workflow_views(
                    session,
                    local_job_id=self._runner.current_job_id,
                    runner_busy=self._runner.is_busy(),
                    lock_path=self._settings.pipeline_lock_path,
                )
        except Exception as exc:  # noqa: BLE001
            handle_poll_error(self._poll_reporter, exc, context="Stuck runs")
            return

        if self._poll_reporter is not None:
            self._poll_reporter.report_success()

        headers = ["State", "Job", "Step", "Phase", "Age", "Reason"]
        rows = [
            (
                view.lifecycle.upper(),
                view.job_id,
                view.step_name,
                view.phase_number,
                view.age_label,
                view.reason,
            )
            for view in self._views
        ]
        self._model.set_data(headers, rows)
        stale_count = sum(1 for view in self._views if view.can_clear)
        self._clear_all_btn.setEnabled(stale_count > 0)
        self._on_selection_changed()

    def _selected_view(self):
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return None
        row = indexes[0].row()
        if row < 0 or row >= len(self._views):
            return None
        return self._views[row]

    def _on_selection_changed(self) -> None:
        view = self._selected_view()
        self._clear_selected_btn.setEnabled(view is not None and view.can_clear)
        self._delete_btn.setEnabled(view is not None)

    def _clear_selected(self) -> None:
        view = self._selected_view()
        if view is None or not view.can_clear:
            return
        if not self._confirm_clear(1):
            return
        self._run_clear([view.step_id])

    def _clear_all_stale(self) -> None:
        stale_ids = [view.step_id for view in self._views if view.can_clear]
        if not stale_ids:
            return
        if not self._confirm_clear(len(stale_ids)):
            return
        self._run_clear(stale_ids)

    def _confirm_clear(self, count: int) -> bool:
        reply = QMessageBox.warning(
            self,
            "Clear stale workflows",
            f"Mark {count} running workflow step(s) as failed?\n\n"
            "Use this when a CLI process was killed but the database still shows running.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _run_clear(self, step_ids: list[uuid.UUID]) -> None:
        try:
            with self._session_factory() as session:
                result = clear_stale_workflow_steps(
                    session,
                    step_ids,
                    local_job_id=self._runner.current_job_id,
                    runner_busy=self._runner.is_busy(),
                    lock_path=self._settings.pipeline_lock_path,
                )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Clear failed", str(exc))
            return

        msg = f"Cleared {result.cleared_steps} step(s)."
        if result.skipped_live:
            msg += f" Skipped {result.skipped_live} live step(s)."
        QMessageBox.information(self, "Workflows cleared", msg)
        self.refresh()
        self.changed.emit()

    def _delete_selected(self) -> None:
        view = self._selected_view()
        if view is None:
            return
        if view.lifecycle == "live":
            QMessageBox.warning(
                self,
                "Cannot delete",
                "The selected workflow appears live. Clear it as stale first or stop the process.",
            )
            return
        reply = QMessageBox.warning(
            self,
            "Delete workflow rows",
            "Delete the selected workflow step row from the database?\n\n"
            "Prefer Clear stale when you only need to unblock the pipeline mutex.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            with self._session_factory() as session:
                deleted = delete_workflow_steps(session, [view.step_id])
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Delete failed", str(exc))
            return
        QMessageBox.information(self, "Deleted", f"Removed {deleted} step row(s).")
        self.refresh()
        self.changed.emit()
