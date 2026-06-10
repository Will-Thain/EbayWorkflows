from __future__ import annotations

import sys
import uuid
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings
from ..operations.progress_report import ProgressSnapshot, format_progress_label
from ..operations.stale_workflows import clear_stale_workflow_steps, list_running_workflow_views
from .job_runner import JobRunner
from ..models_qt import GenericTableModel
from .poll_errors import GuiPollErrorReporter, handle_poll_error
from .theme import apply_tab_layout, configure_data_table
from .workflow_catalog import WORKFLOW_JOBS
from .workflow_monitor import (
    ActiveWorkflow,
    elapsed_label,
    fetch_dashboard_stats,
    fetch_recent_steps,
    fetch_running_workflows,
    resolve_progress,
    workflow_control_flags,
    workflow_source_label,
)
from .widgets import CardFrame, PageHeader, SectionTitle, StatCard, StatusChip


class OngoingWorkflowCard(CardFrame):
    stop_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()
    clear_stale_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("workflowCard", parent)
        self._step_id = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self._title = QLabel()
        self._title.setObjectName("tileTitle")
        header.addWidget(self._title, stretch=1)
        self._status_chip = StatusChip()
        header.addWidget(self._status_chip)
        self._source = QLabel()
        self._source.setObjectName("caption")
        header.addWidget(self._source)
        layout.addLayout(header)

        self._meta = QLabel()
        self._meta.setObjectName("caption")
        self._meta.setWordWrap(True)
        layout.addWidget(self._meta)

        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        layout.addWidget(self._progress)

        self._progress_detail = QLabel()
        self._progress_detail.setObjectName("caption")
        layout.addWidget(self._progress_detail)

        actions = QHBoxLayout()
        self._resume_btn = QPushButton("Start")
        self._resume_btn.setObjectName("secondaryButton")
        self._resume_btn.setToolTip("Resume a paused GUI workflow")
        self._resume_btn.clicked.connect(self.resume_requested.emit)
        actions.addWidget(self._resume_btn)

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setObjectName("secondaryButton")
        self._pause_btn.setToolTip("Pause the GUI workflow process (Windows)")
        self._pause_btn.clicked.connect(self.pause_requested.emit)
        actions.addWidget(self._pause_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.setToolTip("Stop the GUI workflow process")
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        actions.addWidget(self._stop_btn)

        self._clear_btn = QPushButton("Clear stale")
        self._clear_btn.setObjectName("dangerButton")
        self._clear_btn.setToolTip("Mark this hung workflow as failed so new jobs can start")
        self._clear_btn.clicked.connect(self._emit_clear_stale)
        self._clear_btn.setVisible(False)
        actions.addWidget(self._clear_btn)

        actions.addStretch()
        layout.addLayout(actions)

    def _emit_clear_stale(self) -> None:
        if self._step_id:
            self.clear_stale_requested.emit(self._step_id)

    def apply(
        self,
        active: ActiveWorkflow,
        source: str,
        progress: ProgressSnapshot | None,
        *,
        elapsed: str,
        control_flags: dict[str, bool],
        lifecycle: str = "live",
        stale_reason: str = "",
        can_clear_stale: bool = False,
        step_id: str = "",
    ) -> None:
        self._step_id = step_id
        job = WORKFLOW_JOBS.get(active.job_id)
        title = job.label if job else active.job_id
        self._title.setText(title)
        self._source.setText(source)

        chip_state = lifecycle
        if control_flags.get("can_resume"):
            chip_state = "paused"
        elif source == "External" and lifecycle == "live":
            chip_state = "external"
        self._status_chip.set_state(chip_state)

        paused_note = " · paused" if control_flags.get("can_resume") else ""
        detail = stale_reason if lifecycle == "stale" and stale_reason else ""
        meta_parts = [
            f"{active.step_label} · phase {active.step.phase_number} · {elapsed}{paused_note}",
        ]
        if detail:
            meta_parts.append(detail)
        self._meta.setText("\n".join(meta_parts))

        if progress and progress.total > 0:
            self._progress.setRange(0, progress.total)
            self._progress.setValue(min(progress.current, progress.total))
            pct = progress.percent
            self._progress.setFormat(f"{pct}%" if pct is not None else "")
            self._progress_detail.setText(format_progress_label(progress))
        else:
            self._progress.setRange(0, 0)
            self._progress.setFormat("In progress…")
            self._progress_detail.setText("Waiting for progress metrics…")

        self._stop_btn.setEnabled(control_flags.get("can_stop", False))
        self._pause_btn.setEnabled(control_flags.get("can_pause", False))
        self._resume_btn.setEnabled(control_flags.get("can_resume", False))
        self._clear_btn.setVisible(can_clear_stale)
        self._clear_btn.setEnabled(can_clear_stale)

        card_state = ""
        if lifecycle == "stale":
            card_state = "stale"
        elif control_flags.get("can_resume"):
            card_state = "paused"
        elif lifecycle == "warming":
            card_state = "warming"
        self.set_card_state(card_state)

        if source == "External":
            tip = "Started outside the GUI — use the terminal (Ctrl+C) to stop."
            self._stop_btn.setToolTip(tip)
            self._pause_btn.setToolTip(tip)
            self._resume_btn.setToolTip(tip)
        elif sys.platform != "win32":
            self._pause_btn.setToolTip("Pause is only supported on Windows.")
            self._resume_btn.setToolTip("Resume is only supported on Windows.")
        else:
            self._stop_btn.setToolTip("Stop the GUI workflow process")
            self._pause_btn.setToolTip("Pause the GUI workflow process")
            self._resume_btn.setToolTip("Resume a paused GUI workflow")


class DashboardTab(QWidget):
    """Home tab: pipeline summary and ongoing workflow monitor."""

    navigate_to_workflows = Signal()

    def __init__(
        self,
        session_factory,
        job_runner: JobRunner,
        settings: Settings | None = None,
        poll_reporter: GuiPollErrorReporter | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_factory = session_factory
        self._runner = job_runner
        self._settings = settings
        self._poll_reporter = poll_reporter
        self._ongoing_cards: dict[str, OngoingWorkflowCard] = {}

        root = apply_tab_layout(self)

        root.addWidget(
            PageHeader("Dashboard", "Pipeline overview and active workflow runs")
        )

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self._stat_listings = StatCard("Listings")
        self._stat_ranked = StatCard("Ranked", accent="ranked")
        self._stat_favorites = StatCard("Favourites", accent="favorites")
        self._stat_images = StatCard("Images cached", accent="images")
        self._stat_running = StatCard("Running now", accent="running")
        for card in (
            self._stat_listings,
            self._stat_ranked,
            self._stat_favorites,
            self._stat_images,
            self._stat_running,
        ):
            stats_row.addWidget(card)
        root.addLayout(stats_row)

        ongoing_header = QHBoxLayout()
        ongoing_header.addWidget(SectionTitle("Ongoing workflows"))
        ongoing_header.addStretch()
        manage_btn = QPushButton("Manage workflows →")
        manage_btn.setObjectName("linkButton")
        manage_btn.clicked.connect(self.navigate_to_workflows.emit)
        ongoing_header.addWidget(manage_btn)
        root.addLayout(ongoing_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._ongoing_host = QWidget()
        self._ongoing_layout = QVBoxLayout(self._ongoing_host)
        self._ongoing_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._ongoing_layout.setSpacing(10)
        scroll.setWidget(self._ongoing_host)
        root.addWidget(scroll, stretch=2)

        recent_box = QGroupBox("Recent workflow activity")
        recent_layout = QVBoxLayout(recent_box)
        self._recent_table = QTableView()
        configure_data_table(self._recent_table)
        self._recent_model = GenericTableModel(self)
        self._recent_table.setModel(self._recent_model)
        recent_layout.addWidget(self._recent_table)
        root.addWidget(recent_box, stretch=1)

        self._poll = QTimer(self)
        self._poll.setInterval(2000)
        self._poll.timeout.connect(self.refresh)
        self._poll.start()

        self.refresh()

    def refresh(self) -> None:
        local_job_id = self._runner.current_job_id
        try:
            with self._session_factory() as session:
                stats = fetch_dashboard_stats(session)
                running = fetch_running_workflows(session)
                recent_headers, recent_rows = fetch_recent_steps(session, limit=12)
                progress_by_step: dict[str, ProgressSnapshot | None] = {}
                views_by_step: dict[str, Any] = {}
                if self._settings is not None:
                    views = list_running_workflow_views(
                        session,
                        local_job_id=local_job_id,
                        runner_busy=self._runner.is_busy(),
                        lock_path=self._settings.pipeline_lock_path,
                    )
                    views_by_step = {str(view.step_id): view for view in views}
                for active in running:
                    progress_by_step[str(active.step.id)] = resolve_progress(session, active)
        except Exception as exc:  # noqa: BLE001
            handle_poll_error(self._poll_reporter, exc, context="Dashboard")
            return

        if self._poll_reporter is not None:
            self._poll_reporter.report_success()

        self._stat_listings.set_value(f"{stats.listing_count:,}")
        self._stat_ranked.set_value(f"{stats.ranked_count:,}")
        self._stat_favorites.set_value(f"{stats.favorite_count:,}")
        self._stat_images.set_value(f"{stats.images_cached:,}")
        self._stat_running.set_value(str(stats.running_count))

        self._sync_ongoing_cards(running, local_job_id, progress_by_step, views_by_step)
        self._recent_model.set_data(recent_headers, recent_rows)

    def _sync_ongoing_cards(
        self,
        running: list[ActiveWorkflow],
        local_job_id: str | None,
        progress_by_step: dict[str, ProgressSnapshot | None],
        views_by_step: dict[str, Any],
    ) -> None:
        active_ids = {str(item.step.id) for item in running}

        for step_id in list(self._ongoing_cards):
            if step_id not in active_ids:
                card = self._ongoing_cards.pop(step_id)
                self._ongoing_layout.removeWidget(card)
                card.deleteLater()

        if not running:
            if self._ongoing_layout.count() == 0:
                empty = QLabel("No workflows are running.")
                empty.setObjectName("emptyState")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._ongoing_layout.addWidget(empty)
            return

        empty = self._ongoing_host.findChild(QLabel, "emptyState")
        if empty is not None:
            self._ongoing_layout.removeWidget(empty)
            empty.deleteLater()

        for active in running:
            step_id = str(active.step.id)
            source = workflow_source_label(active, local_job_id)
            flags = workflow_control_flags(
                source=source,
                runner_busy=self._runner.is_busy(),
                runner_paused=self._runner.is_paused(),
                matches_local_job=local_job_id == active.job_id,
            )

            card = self._ongoing_cards.get(step_id)
            if card is None:
                card = OngoingWorkflowCard(self._ongoing_host)
                card.stop_requested.connect(self._request_stop)
                card.pause_requested.connect(self._request_pause)
                card.resume_requested.connect(self._request_resume)
                card.clear_stale_requested.connect(self._request_clear_stale)
                self._ongoing_cards[step_id] = card
                self._ongoing_layout.addWidget(card)

            view = views_by_step.get(step_id)
            card.apply(
                active,
                source,
                progress_by_step.get(step_id),
                elapsed=elapsed_label(active.step),
                control_flags=flags,
                lifecycle=view.lifecycle if view else "live",
                stale_reason=view.reason if view else "",
                can_clear_stale=bool(view and view.can_clear),
                step_id=step_id,
            )

    def _request_stop(self) -> None:
        if not self._runner.is_busy():
            return
        self._runner.stop()

    def _request_pause(self) -> None:
        try:
            self._runner.pause()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Pause failed", str(exc))

    def _request_resume(self) -> None:
        try:
            self._runner.resume()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Resume failed", str(exc))

    def _request_clear_stale(self, step_id: str) -> None:
        if self._settings is None:
            return
        reply = QMessageBox.warning(
            self,
            "Clear stale workflow",
            "Mark this hung workflow as failed so new jobs can start?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            with self._session_factory() as session:
                result = clear_stale_workflow_steps(
                    session,
                    [uuid.UUID(step_id)],
                    local_job_id=self._runner.current_job_id,
                    runner_busy=self._runner.is_busy(),
                    lock_path=self._settings.pipeline_lock_path,
                )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Clear failed", str(exc))
            return
        if result.cleared_steps == 0:
            QMessageBox.information(self, "Not cleared", "Workflow is still live or already finished.")
        self.refresh()
