from __future__ import annotations

import uuid
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from PySide6.QtCore import QDateTime, QTime, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import select

from ..models import ScheduledJob
from ..scheduler_service import (
    create_scheduled_job,
    fetch_due_schedules,
    refresh_next_run_at,
    try_dispatch_one_due,
)
from .job_runner import JobRunner
from ..models_qt import GenericTableModel
from .workflow_catalog import LONG_RUNNING_SCHEDULE_JOBS, WORKFLOW_JOBS


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


class ScheduleEditorDialog(QDialog):
    def __init__(
        self,
        session_factory,
        existing: ScheduledJob | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_factory = session_factory
        self._existing = existing
        self.setWindowTitle("Edit schedule" if existing else "New schedule")
        self.setMinimumWidth(420)

        form = QFormLayout(self)

        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Nightly ingest")
        form.addRow("Name:", self._name)

        self._job = QComboBox()
        for job_id, job in WORKFLOW_JOBS.items():
            self._job.addItem(job.label, job_id)
        form.addRow("Job:", self._job)

        self._type = QComboBox()
        self._type.addItem("Every N hours", "interval")
        self._type.addItem("Daily at time", "daily")
        self._type.addItem("Once", "once")
        self._type.currentIndexChanged.connect(self._sync_type_fields)
        form.addRow("Schedule:", self._type)

        self._interval = QDoubleSpinBox()
        self._interval.setRange(1, 168 * 7)
        self._interval.setValue(24)
        self._interval.setSuffix(" h")
        form.addRow("Interval:", self._interval)

        self._daily_time = QTimeEdit()
        self._daily_time.setDisplayFormat("HH:mm")
        self._daily_time.setTime(QTime(6, 0))
        form.addRow("Daily at:", self._daily_time)

        self._once_dt = QDateTimeEdit()
        self._once_dt.setCalendarPopup(True)
        self._once_dt.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        form.addRow("Run once:", self._once_dt)

        self._tz = QComboBox()
        self._tz.setEditable(True)
        for tz_name in ("UTC", "Europe/London", "America/New_York", "America/Los_Angeles"):
            self._tz.addItem(tz_name)
        form.addRow("Timezone:", self._tz)

        self._enabled = QCheckBox("Enabled")
        self._enabled.setChecked(True)
        form.addRow(self._enabled)

        self._catch_up = QCheckBox("Catch up one missed run on next check")
        form.addRow(self._catch_up)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if existing:
            self._load_existing(existing)
        self._sync_type_fields()

    def _load_existing(self, row: ScheduledJob) -> None:
        self._name.setText(row.name)
        idx = self._job.findData(row.job_id)
        if idx >= 0:
            self._job.setCurrentIndex(idx)
        tidx = self._type.findData(row.schedule_type)
        if tidx >= 0:
            self._type.setCurrentIndex(tidx)
        if row.interval_hours is not None:
            self._interval.setValue(float(row.interval_hours))
        if row.daily_at is not None:
            self._daily_time.setTime(QTime(row.daily_at.hour, row.daily_at.minute))
        if row.run_at is not None:
            run_at = row.run_at
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
            self._once_dt.setDateTime(QDateTime(run_at.astimezone()))
        self._tz.setCurrentText(row.timezone)
        self._enabled.setChecked(row.enabled)
        self._catch_up.setChecked(row.catch_up_missed)

    def _sync_type_fields(self) -> None:
        schedule_type = str(self._type.currentData())
        self._interval.setEnabled(schedule_type == "interval")
        self._daily_time.setEnabled(schedule_type == "daily")
        self._once_dt.setEnabled(schedule_type == "once")

    def _save(self) -> None:
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        schedule_type = str(self._type.currentData())
        job_id = str(self._job.currentData())
        tz_name = self._tz.currentText().strip() or "UTC"
        try:
            ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            QMessageBox.warning(self, "Validation", f"Unknown timezone: {tz_name}")
            return

        interval_hours: float | None = None
        daily_at: time | None = None
        run_at: datetime | None = None
        if schedule_type == "interval":
            interval_hours = float(self._interval.value())
            if interval_hours < 1:
                QMessageBox.warning(self, "Validation", "Interval must be at least 1 hour.")
                return
        elif schedule_type == "daily":
            qt = self._daily_time.time()
            daily_at = time(qt.hour(), qt.minute())
        else:
            run_at = self._once_dt.dateTime().toPython()
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=datetime.now().astimezone().tzinfo)
            run_at = run_at.astimezone(timezone.utc)
            if run_at <= datetime.now(timezone.utc):
                QMessageBox.warning(self, "Validation", "One-time run must be in the future.")
                return

        if job_id in LONG_RUNNING_SCHEDULE_JOBS:
            reply = QMessageBox.warning(
                self,
                "Long-running job",
                f"{job_id} can run for many hours and needs GPU/network/OCR. "
                "Scheduling it is discouraged; run manually from Workflows instead. Save anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            with self._session_factory() as session:
                if self._existing:
                    row = session.get(ScheduledJob, self._existing.id)
                    if row is None:
                        raise ValueError("Schedule was deleted.")
                    row.name = name
                    row.job_id = job_id
                    row.schedule_type = schedule_type
                    row.interval_hours = interval_hours
                    row.daily_at = daily_at
                    row.run_at = run_at
                    row.timezone = tz_name
                    row.enabled = self._enabled.isChecked()
                    row.catch_up_missed = self._catch_up.isChecked()
                    row.updated_at = datetime.now(timezone.utc)
                    refresh_next_run_at(session, row)
                else:
                    create_scheduled_job(
                        session,
                        name=name,
                        job_id=job_id,
                        job_params_json={},
                        schedule_type=schedule_type,
                        interval_hours=interval_hours,
                        daily_at=daily_at,
                        run_at=run_at,
                        timezone_name=tz_name,
                        enabled=self._enabled.isChecked(),
                        catch_up_missed=self._catch_up.isChecked(),
                    )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.accept()


class SchedulesPanel(QWidget):
    def __init__(
        self,
        session_factory,
        job_runner: JobRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_factory = session_factory
        self._runner = job_runner

        layout = QVBoxLayout(self)
        hint = QLabel(
            "Schedules run while this app is open (checks every minute). "
            "For 24/7 automation, use Windows Task Scheduler with "
            "`ebay-workflows run-due-schedules`."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        layout.addWidget(hint)

        toolbar = QHBoxLayout()
        new_btn = QPushButton("New…")
        new_btn.clicked.connect(self._new_schedule)
        toolbar.addWidget(new_btn)
        edit_btn = QPushButton("Edit…")
        edit_btn.clicked.connect(self._edit_schedule)
        toolbar.addWidget(edit_btn)
        toggle_btn = QPushButton("Enable / Disable")
        toggle_btn.clicked.connect(self._toggle_enabled)
        toolbar.addWidget(toggle_btn)
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_schedule)
        toolbar.addWidget(delete_btn)
        run_btn = QPushButton("Run due now")
        run_btn.clicked.connect(self._run_due_now)
        toolbar.addWidget(run_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._table = QTableView()
        self._model = GenericTableModel(self)
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table)

        self._schedule_ids: list[str] = []

        self._poll = QTimer(self)
        self._poll.setInterval(60_000)
        self._poll.timeout.connect(self._tick_in_app)
        self._poll.start()

        self.refresh()

    def _selected_id(self) -> uuid.UUID | None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return None
        row = indexes[0].row()
        if row < 0 or row >= len(self._schedule_ids):
            return None
        return uuid.UUID(self._schedule_ids[row])

    def refresh(self) -> None:
        headers = ["Name", "Job", "Type", "Next run", "Last run", "Status", "On"]
        rows: list[tuple[Any, ...]] = []
        self._schedule_ids = []
        try:
            with self._session_factory() as session:
                schedules = list(
                    session.execute(
                        select(ScheduledJob).order_by(ScheduledJob.name.asc())
                    ).scalars()
                )
                for row in schedules:
                    self._schedule_ids.append(str(row.id))
                    job_label = WORKFLOW_JOBS.get(row.job_id)
                    job_name = job_label.label if job_label else row.job_id
                    type_label = row.schedule_type
                    if row.schedule_type == "interval" and row.interval_hours:
                        type_label = f"every {row.interval_hours:g}h"
                    rows.append(
                        (
                            row.name,
                            job_name,
                            type_label,
                            _format_dt(row.next_run_at),
                            _format_dt(row.last_run_at),
                            row.last_run_status or "—",
                            "yes" if row.enabled else "no",
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Load failed", str(exc))
            return
        self._model.set_data(headers, rows)

    def _new_schedule(self) -> None:
        dialog = ScheduleEditorDialog(self._session_factory, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _edit_schedule(self) -> None:
        selected = self._selected_id()
        if not selected:
            QMessageBox.information(self, "Edit", "Select a schedule first.")
            return
        with self._session_factory() as session:
            row = session.get(ScheduledJob, selected)
        if row is None:
            self.refresh()
            return
        dialog = ScheduleEditorDialog(self._session_factory, existing=row, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _toggle_enabled(self) -> None:
        selected = self._selected_id()
        if not selected:
            return
        with self._session_factory() as session:
            row = session.get(ScheduledJob, selected)
            if row is None:
                return
            row.enabled = not row.enabled
            if row.enabled:
                refresh_next_run_at(session, row)
            else:
                row.updated_at = datetime.now(timezone.utc)
                session.commit()
        self.refresh()

    def _delete_schedule(self) -> None:
        selected = self._selected_id()
        if not selected:
            return
        reply = QMessageBox.question(
            self,
            "Delete schedule",
            "Delete this schedule permanently?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        with self._session_factory() as session:
            row = session.get(ScheduledJob, selected)
            if row:
                session.delete(row)
                session.commit()
        self.refresh()

    def _run_due_now(self) -> None:
        due_count = 0
        try:
            with self._session_factory() as session:
                due_count = len(fetch_due_schedules(session, limit=20))
                dispatched = try_dispatch_one_due(session, use_gui_runner=self._runner)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Dispatch failed", str(exc))
            return
        if dispatched:
            QMessageBox.information(
                self,
                "Dispatched",
                f"Started scheduled job “{dispatched.name}” ({dispatched.job_id}).",
            )
        elif due_count:
            QMessageBox.information(
                self,
                "Busy",
                "A workflow is already running; due schedules were skipped.",
            )
        else:
            QMessageBox.information(self, "Nothing due", "No enabled schedules are due right now.")
        self.refresh()

    def _tick_in_app(self) -> None:
        try:
            with self._session_factory() as session:
                try_dispatch_one_due(session, use_gui_runner=self._runner)
        except Exception:  # noqa: BLE001
            return
        self.refresh()
