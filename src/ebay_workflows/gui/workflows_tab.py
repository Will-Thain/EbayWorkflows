from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings
from ..services.progress_report import ProgressSnapshot, format_progress_label, parse_progress_line
from .job_runner import JobRunner
from .poll_errors import GuiPollErrorReporter, handle_poll_error
from .progress_estimates import estimate_job_total, poll_job_progress
from .schedules_panel import SchedulesPanel
from .stale_workflows_panel import StaleWorkflowsPanel
from .theme import apply_tab_layout
from .workflow_catalog import WORKFLOW_JOBS, WORKFLOW_LAUNCH_ORDER
from .workflow_monitor import elapsed_label, fetch_active_workflow, resolve_progress
from .widgets import PageHeader, SectionTitle, WorkflowTile


class WorkflowsTab(QWidget):
    def __init__(
        self,
        settings: Settings,
        session_factory,
        job_runner: JobRunner,
        on_ranking_refresh,
        poll_reporter: GuiPollErrorReporter | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._session_factory = session_factory
        self._runner = job_runner
        self._on_ranking_refresh = on_ranking_refresh
        self._poll_reporter = poll_reporter
        self._active_job_id: str | None = None
        self._monitored_step_id: str | None = None
        self._last_external_job_id: str | None = None
        self._progress_snapshot = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        inner_tabs = QTabWidget()
        run_now = QWidget()
        run_layout = apply_tab_layout(run_now)

        run_layout.addWidget(
            PageHeader("Run workflow", "Start a pipeline phase manually from the GUI")
        )

        jobs_box = QGroupBox("Available workflows")
        jobs_layout = QGridLayout(jobs_box)
        jobs_layout.setHorizontalSpacing(10)
        jobs_layout.setVerticalSpacing(10)
        self._job_tiles: dict[str, WorkflowTile] = {}
        columns = 3
        for index, job_id in enumerate(WORKFLOW_LAUNCH_ORDER):
            job = WORKFLOW_JOBS[job_id]
            tile = WorkflowTile(job_id, job.label, job.duration_tier)
            tile.run_requested.connect(self._start_job)
            row, col = divmod(index, columns)
            jobs_layout.addWidget(tile, row, col)
            self._job_tiles[job_id] = tile
        run_layout.addWidget(jobs_box)

        params_box = QGroupBox("Ingest (phase 1) options")
        params = QHBoxLayout(params_box)
        params.addWidget(QLabel("Query (phase 1):"))
        self._query_edit = QLineEdit("magic the gathering")
        params.addWidget(self._query_edit, stretch=1)
        params.addWidget(QLabel("Max pages:"))
        self._max_pages = QSpinBox()
        self._max_pages.setRange(1, 200)
        self._max_pages.setValue(20)
        params.addWidget(self._max_pages)
        run_layout.addWidget(params_box)

        transport = QHBoxLayout()
        transport.addWidget(SectionTitle("Transport"))
        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setObjectName("secondaryButton")
        self._pause_btn.setToolTip("Pause or resume the running GUI workflow (Windows)")
        self._pause_btn.clicked.connect(self._toggle_pause)
        self._pause_btn.setEnabled(False)
        transport.addWidget(self._pause_btn)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.setToolTip("Stop the running GUI workflow")
        self._stop_btn.clicked.connect(self._runner.stop)
        self._stop_btn.setEnabled(False)
        transport.addWidget(self._stop_btn)
        transport.addStretch()
        run_layout.addLayout(transport)

        self._phase_status = QLabel("Idle")
        self._phase_status.setObjectName("caption")
        run_layout.addWidget(self._phase_status)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("—")
        run_layout.addWidget(self._progress_bar)

        self._progress_label = QLabel("")
        self._progress_label.setObjectName("caption")
        run_layout.addWidget(self._progress_label)

        self._log = QPlainTextEdit()
        self._log.setObjectName("logPanel")
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("CLI output appears here…")
        run_layout.addWidget(self._log, stretch=1)

        inner_tabs.addTab(run_now, "Run now")
        inner_tabs.addTab(SchedulesPanel(session_factory, job_runner), "Schedules")
        self._stale_panel = StaleWorkflowsPanel(
            settings, session_factory, job_runner, poll_reporter=poll_reporter
        )
        self._stale_panel.changed.connect(self._poll_workflow_status)
        inner_tabs.addTab(self._stale_panel, "Stuck runs")
        layout.addWidget(inner_tabs)

        self._runner.log_line.connect(self._append_log)
        self._runner.job_started.connect(self._on_job_started)
        self._runner.job_finished.connect(self._on_job_finished)
        self._runner.job_paused.connect(self._on_job_paused)
        self._runner.job_resumed.connect(self._on_job_resumed)

        self._poll = QTimer(self)
        self._poll.setInterval(2000)
        self._poll.timeout.connect(self._poll_workflow_status)
        self._poll.start()

    def _append_log(self, line: str) -> None:
        self._log.appendPlainText(line)
        snapshot = parse_progress_line(line)
        if snapshot:
            self._apply_progress(snapshot)

    def _reset_progress(self) -> None:
        self._progress_snapshot = None
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setFormat("Starting…")
        self._progress_label.setText("")

    def _apply_progress(self, snapshot) -> None:
        self._progress_snapshot = snapshot
        if snapshot.total > 0:
            self._progress_bar.setRange(0, snapshot.total)
            self._progress_bar.setValue(min(snapshot.current, snapshot.total))
            pct = snapshot.percent
            self._progress_bar.setFormat(f"{pct}%" if pct is not None else "")
        else:
            self._progress_bar.setRange(0, 0)
            self._progress_bar.setFormat("…")
        self._progress_label.setText(format_progress_label(snapshot))

    def _job_params(self, job_id: str) -> dict[str, Any]:
        if job_id == "phase1":
            return {
                "query": self._query_edit.text().strip() or "magic the gathering",
                "max_pages": self._max_pages.value(),
                "page_size": self._settings.ebay_page_size,
                "download_images": True,
            }
        if job_id == "phase2":
            return {"top_k": 3}
        if job_id == "phase4":
            return {"hybrid": True}
        return {}

    def _start_job(self, job_id: str) -> None:
        if job_id in ("phase5", "phase6") and self._confirm_long_job(job_id) is False:
            return
        try:
            self._runner.start(job_id, self._job_params(job_id))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Start failed", str(exc))

    def _toggle_pause(self) -> None:
        try:
            if self._runner.is_paused():
                self._runner.resume()
            else:
                self._runner.pause()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Pause failed", str(exc))

    def _sync_transport_buttons(self, *, local_running: bool, external: bool) -> None:
        paused = self._runner.is_paused()
        pause_supported = sys.platform == "win32"
        active_id = self._active_job_id if local_running else self._last_external_job_id
        if external:
            self._set_job_tiles_enabled(False, active_job_id=active_id)
            self._pause_btn.setEnabled(False)
            self._pause_btn.setText("Pause")
            self._stop_btn.setEnabled(False)
            self._stop_btn.setToolTip(
                "This job was started outside the GUI. Stop it from the terminal (Ctrl+C)."
            )
            return

        self._stop_btn.setToolTip("Stop the running GUI workflow")
        if local_running:
            self._set_job_tiles_enabled(False, active_job_id=active_id)
            self._stop_btn.setEnabled(True)
            if paused:
                self._pause_btn.setText("Resume")
                self._pause_btn.setEnabled(pause_supported)
            else:
                self._pause_btn.setText("Pause")
                self._pause_btn.setEnabled(pause_supported)
            if not pause_supported:
                self._pause_btn.setToolTip("Pause is only supported on Windows.")
        else:
            self._set_job_tiles_enabled(True)
            self._pause_btn.setEnabled(False)
            self._pause_btn.setText("Pause")
            self._stop_btn.setEnabled(False)

    def _set_job_tiles_enabled(
        self,
        enabled: bool,
        *,
        active_job_id: str | None = None,
    ) -> None:
        for job_id, tile in self._job_tiles.items():
            tile.set_enabled(enabled)
            tile.set_active(not enabled and job_id == active_job_id)

    def _on_job_paused(self, job_id: str) -> None:
        self._phase_status.setText(f"Paused: {job_id}")
        self._sync_transport_buttons(local_running=True, external=False)

    def _on_job_resumed(self, job_id: str) -> None:
        self._phase_status.setText(f"Running: {job_id}")
        self._sync_transport_buttons(local_running=True, external=False)

    def _confirm_long_job(self, job_id: str) -> bool:
        job = WORKFLOW_JOBS.get(job_id)
        label = job.label if job else job_id
        reply = QMessageBox.warning(
            self,
            "Long-running job",
            f"{label} may run for hours and needs network/Tesseract for OCR. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _on_job_started(self, job_id: str) -> None:
        self._active_job_id = job_id
        self._sync_transport_buttons(local_running=True, external=False)
        self._phase_status.setText(f"Running: {job_id}")
        self._reset_progress()
        try:
            with self._session_factory() as session:
                estimate = estimate_job_total(session, job_id, self._job_params(job_id))
            if estimate:
                total, unit = estimate
                self._progress_bar.setRange(0, total)
                self._progress_bar.setValue(0)
                self._progress_bar.setFormat("0%")
                self._progress_label.setText(f"0 / {total:,} {unit}")
        except Exception:  # noqa: BLE001
            pass

    def _on_job_finished(self, exit_code: int, job_id: str) -> None:
        self._active_job_id = None
        self._sync_transport_buttons(local_running=False, external=False)
        if self._progress_snapshot and self._progress_snapshot.total > 0:
            done = self._progress_snapshot
            self._progress_bar.setRange(0, done.total)
            self._progress_bar.setValue(done.total)
            self._progress_bar.setFormat("100%")
            self._progress_label.setText(format_progress_label(done))
        else:
            self._progress_bar.setRange(0, 100)
            self._progress_bar.setValue(100 if exit_code == 0 else 0)
            self._progress_bar.setFormat("Done" if exit_code == 0 else "Failed")
        self._poll_workflow_status()
        if job_id in ("phase4", "phase3", "phase2"):
            self._on_ranking_refresh()
        if not self._monitored_step_id:
            self._sync_transport_buttons(local_running=False, external=False)
        if not self._runner.is_busy() and self._monitored_step_id is None:
            if exit_code != 0:
                self._phase_status.setText(f"Finished {job_id} with errors (exit {exit_code})")
            else:
                self._phase_status.setText(f"Finished {job_id} successfully")

    def _on_external_finished(self, job_id: str | None) -> None:
        self._monitored_step_id = None
        self._last_external_job_id = None
        if self._runner.is_busy():
            return
        self._sync_transport_buttons(local_running=False, external=False)
        self._phase_status.setText("Idle")
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(100)
        self._progress_bar.setFormat("Done")
        if job_id in ("phase4", "phase3", "phase2"):
            self._on_ranking_refresh()

    def _poll_workflow_status(self) -> None:
        local_busy = self._runner.is_busy()
        active = None
        try:
            with self._session_factory() as session:
                active = fetch_active_workflow(session)
                if active is None:
                    if self._monitored_step_id:
                        finished_job = self._last_external_job_id
                        self._on_external_finished(finished_job)
                    elif not local_busy and self._phase_status.text().startswith("External:"):
                        self._phase_status.setText("Idle")
                    if self._poll_reporter is not None:
                        self._poll_reporter.report_success()
                    return

                step_id = str(active.step.id)
                external = not local_busy or self._active_job_id != active.job_id

                if external:
                    if self._monitored_step_id != step_id:
                        self._log.appendPlainText(
                            f"Monitoring external workflow: {active.step_label} "
                            "(started outside GUI; logs unavailable here)."
                        )
                    self._monitored_step_id = step_id
                    self._last_external_job_id = active.job_id
                    self._sync_transport_buttons(local_running=False, external=True)
                    elapsed = elapsed_label(active.step)
                    job_label = WORKFLOW_JOBS.get(active.job_id)
                    label = job_label.label if job_label else active.job_id
                    self._phase_status.setText(
                        f"External: {label} — {active.step_label} ({elapsed}, no live log)"
                    )
                    snap = resolve_progress(session, active)
                    if snap:
                        self._apply_progress(snap)
                else:
                    self._monitored_step_id = step_id
                    self._sync_transport_buttons(local_running=True, external=False)
                    self._phase_status.setText(
                        f"Running: {active.job_id} — {active.step_label} (phase {active.step.phase_number})"
                    )
                    if self._progress_snapshot is None and self._active_job_id:
                        polled = poll_job_progress(session, self._active_job_id)
                        if polled:
                            current, total, unit = polled
                            self._apply_progress(
                                ProgressSnapshot(current=current, total=total, unit=unit)
                            )
                    elif self._active_job_id:
                        snap = resolve_progress(session, active)
                        if snap and (
                            self._progress_snapshot is None
                            or snap.current > self._progress_snapshot.current
                        ):
                            self._apply_progress(snap)
        except Exception as exc:  # noqa: BLE001
            handle_poll_error(self._poll_reporter, exc, context="Workflow progress")
            return
        if self._poll_reporter is not None:
            self._poll_reporter.report_success()
