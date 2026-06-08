from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
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

from ..services.progress_report import ProgressSnapshot, format_progress_label
from .job_runner import JobRunner
from .models_qt import GenericTableModel
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


class StatCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        self._value = QLabel("—")
        self._value.setStyleSheet("font-size: 22px; font-weight: bold;")
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._value)
        caption = QLabel(title)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setStyleSheet("color: palette(mid);")
        layout.addWidget(caption)

    def set_value(self, text: str) -> None:
        self._value.setText(text)


class OngoingWorkflowCard(QFrame):
    stop_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)

        header = QHBoxLayout()
        self._title = QLabel()
        self._title.setStyleSheet("font-weight: bold; font-size: 13px;")
        header.addWidget(self._title, stretch=1)
        self._source = QLabel()
        self._source.setStyleSheet("font-size: 11px; color: palette(mid);")
        header.addWidget(self._source)
        layout.addLayout(header)

        self._meta = QLabel()
        self._meta.setWordWrap(True)
        layout.addWidget(self._meta)

        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        layout.addWidget(self._progress)

        self._progress_detail = QLabel()
        layout.addWidget(self._progress_detail)

        actions = QHBoxLayout()
        self._resume_btn = QPushButton("▶ Start")
        self._resume_btn.setToolTip("Resume a paused GUI workflow (Start)")
        self._resume_btn.clicked.connect(self.resume_requested.emit)
        actions.addWidget(self._resume_btn)

        self._pause_btn = QPushButton("⏸ Pause")
        self._pause_btn.setToolTip("Pause the GUI workflow process (Windows)")
        self._pause_btn.clicked.connect(self.pause_requested.emit)
        actions.addWidget(self._pause_btn)

        self._stop_btn = QPushButton("⏹ Stop")
        self._stop_btn.setToolTip("Stop the GUI workflow process")
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        actions.addWidget(self._stop_btn)

        actions.addStretch()
        layout.addLayout(actions)

    def apply(
        self,
        active: ActiveWorkflow,
        source: str,
        progress: ProgressSnapshot | None,
        *,
        elapsed: str,
        control_flags: dict[str, bool],
    ) -> None:
        job = WORKFLOW_JOBS.get(active.job_id)
        title = job.label if job else active.job_id
        self._title.setText(title)
        self._source.setText(source)
        paused_note = " · paused" if control_flags.get("can_resume") else ""
        self._meta.setText(
            f"{active.step_label} · phase {active.step.phase_number} · {elapsed}{paused_note}"
        )

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

        can_stop = control_flags.get("can_stop", False)
        can_pause = control_flags.get("can_pause", False)
        can_resume = control_flags.get("can_resume", False)

        self._stop_btn.setEnabled(can_stop)
        self._pause_btn.setEnabled(can_pause)
        self._resume_btn.setEnabled(can_resume)

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

        paused = control_flags.get("can_resume", False)
        if paused:
            self.setStyleSheet(
                "border: 2px solid palette(highlight);"
                " background: palette(alternate-base);"
                " border-radius: 6px;"
            )
        else:
            self.setStyleSheet("")


class DashboardTab(QWidget):
    """Home tab: pipeline summary and ongoing workflow monitor."""

    navigate_to_workflows = Signal()

    def __init__(
        self,
        session_factory,
        job_runner: JobRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_factory = session_factory
        self._runner = job_runner
        self._ongoing_cards: dict[str, OngoingWorkflowCard] = {}

        root = QVBoxLayout(self)
        root.setSpacing(16)

        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(title)

        stats_row = QHBoxLayout()
        self._stat_listings = StatCard("Listings")
        self._stat_ranked = StatCard("Ranked")
        self._stat_favorites = StatCard("Favourites")
        self._stat_images = StatCard("Images cached")
        self._stat_running = StatCard("Running now")
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
        ongoing_header.addWidget(QLabel("Ongoing workflows"))
        ongoing_header.addStretch()
        manage_btn = QPushButton("Manage workflows →")
        manage_btn.clicked.connect(self.navigate_to_workflows.emit)
        ongoing_header.addWidget(manage_btn)
        root.addLayout(ongoing_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._ongoing_host = QWidget()
        self._ongoing_layout = QVBoxLayout(self._ongoing_host)
        self._ongoing_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._ongoing_host)
        root.addWidget(scroll, stretch=2)

        recent_box = QGroupBox("Recent workflow activity")
        recent_layout = QVBoxLayout(recent_box)
        self._recent_table = QTableView()
        self._recent_model = GenericTableModel(self)
        self._recent_table.setModel(self._recent_model)
        self._recent_table.setAlternatingRowColors(True)
        self._recent_table.horizontalHeader().setStretchLastSection(True)
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
                for active in running:
                    progress_by_step[str(active.step.id)] = resolve_progress(session, active)
        except Exception:  # noqa: BLE001
            return

        self._stat_listings.set_value(f"{stats.listing_count:,}")
        self._stat_ranked.set_value(f"{stats.ranked_count:,}")
        self._stat_favorites.set_value(f"{stats.favorite_count:,}")
        self._stat_images.set_value(f"{stats.images_cached:,}")
        self._stat_running.set_value(str(stats.running_count))

        self._sync_ongoing_cards(running, local_job_id, progress_by_step)
        self._recent_model.set_data(recent_headers, recent_rows)

    def _sync_ongoing_cards(
        self,
        running: list[ActiveWorkflow],
        local_job_id: str | None,
        progress_by_step: dict[str, ProgressSnapshot | None],
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
                empty.setObjectName("ongoing_empty")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty.setStyleSheet("color: palette(mid); padding: 24px;")
                self._ongoing_layout.addWidget(empty)
            return

        empty = self._ongoing_host.findChild(QLabel, "ongoing_empty")
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
                self._ongoing_cards[step_id] = card
                self._ongoing_layout.addWidget(card)

            card.apply(
                active,
                source,
                progress_by_step.get(step_id),
                elapsed=elapsed_label(active.step),
                control_flags=flags,
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
