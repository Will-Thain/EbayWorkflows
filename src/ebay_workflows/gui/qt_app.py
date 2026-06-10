from __future__ import annotations

import csv
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QSize
from PySide6.QtGui import QDesktopServices, QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from ..config import Settings
from ..db import build_session_factory
from ..operations.match_stats import collect_match_stats
from .dashboard_tab import DashboardTab
from .job_runner import JobRunner
from .poll_errors import GuiPollErrorReporter, handle_poll_error
from .workflows_tab import WorkflowsTab
from .workflow_catalog import WORKFLOW_JOBS
from .workflow_monitor import (
    elapsed_label,
    fetch_dashboard_stats,
    fetch_running_workflows,
    resolve_progress,
)
from ..operations.ranked_export import RankedListingRow, fetch_ranked_listings
from . import favorites as fav
from .db_browser import CURATED_QUERIES, run_curated_query
from .listing_detail import fetch_listing_detail
from .match_widgets import ListingDetailPanel
from ..models_qt import GenericTableModel, RankedListTableModel
from .theme import apply_tab_layout, configure_data_table


class OpportunitiesTab(QWidget):
    def __init__(self, settings: Settings, session_factory, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._session_factory = session_factory
        self._rows: list[RankedListingRow] = []
        self._selected_id: uuid.UUID | None = None

        layout = apply_tab_layout(self)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Show:"))
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All ranked", "Favourites only"])
        self._filter_combo.currentIndexChanged.connect(lambda _: self.refresh())
        toolbar.addWidget(self._filter_combo)

        toolbar.addWidget(QLabel("Limit:"))
        self._limit_combo = QComboBox()
        self._limit_combo.addItems(["25", "50", "100", "200"])
        self._limit_combo.setCurrentText("50")
        self._limit_combo.currentIndexChanged.connect(lambda _: self.refresh())
        toolbar.addWidget(self._limit_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(refresh_btn)

        self._open_ebay_btn = QPushButton("Open on eBay")
        self._open_ebay_btn.setObjectName("primaryButton")
        self._open_ebay_btn.clicked.connect(self._open_ebay)
        self._open_ebay_btn.setEnabled(False)
        toolbar.addWidget(self._open_ebay_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._table = QTableView()
        self._model = RankedListTableModel(self)
        self._table.setModel(self._model)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.setSortingEnabled(True)
        configure_data_table(self._table)
        self._table.verticalHeader().setDefaultSectionSize(52)
        self._table.setIconSize(QSize(48, 48))
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._table)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)

        self._title_label = QLabel("Select a listing")
        self._title_label.setWordWrap(True)
        self._title_label.setObjectName("sectionTitle")
        detail_layout.addWidget(self._title_label)

        self._meta_label = QLabel("")
        self._meta_label.setObjectName("caption")
        self._meta_label.setWordWrap(True)
        detail_layout.addWidget(self._meta_label)

        fav_box = QGroupBox("Favourite")
        fav_form = QFormLayout(fav_box)
        self._fav_btn = QPushButton("☆ Favourite")
        self._fav_btn.setObjectName("secondaryButton")
        self._fav_btn.clicked.connect(self._toggle_favorite)
        self._fav_btn.setEnabled(False)
        fav_form.addRow(self._fav_btn)
        self._note_edit = QLineEdit()
        self._note_edit.setPlaceholderText("Optional note")
        fav_form.addRow("Note:", self._note_edit)
        save_note_btn = QPushButton("Save note")
        save_note_btn.clicked.connect(self._save_note)
        fav_form.addRow(save_note_btn)
        detail_layout.addWidget(fav_box)

        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        self._detail_panel = ListingDetailPanel()
        detail_scroll.setWidget(self._detail_panel)
        detail_layout.addWidget(detail_scroll, stretch=1)

        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def refresh(self) -> None:
        try:
            limit = int(self._limit_combo.currentText())
        except ValueError:
            limit = 50
        favorites_only = self._filter_combo.currentIndex() == 1

        try:
            with self._session_factory() as session:
                self._rows = fetch_ranked_listings(
                    session, limit=limit, favorites_only=favorites_only
                )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Database error", str(exc))
            return

        self._model.set_rows(self._rows)
        self._table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._selected_id = None
        self._title_label.setText("Select a listing")
        self._meta_label.setText("")
        self._detail_panel.set_detail(None)
        self._fav_btn.setEnabled(False)
        self._open_ebay_btn.setEnabled(False)

    def _row_for_id(self, listing_id: str) -> RankedListingRow | None:
        for row in self._rows:
            if row.listing_id == listing_id:
                return row
        return None

    def _on_selection_changed(self) -> None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return
        listing_id = indexes[0].data(Qt.ItemDataRole.UserRole)
        if not listing_id:
            return

        row = self._row_for_id(str(listing_id))
        if not row:
            return

        self._selected_id = uuid.UUID(str(listing_id))
        self._title_label.setText(row.title)
        ship = f"{row.shipping_amount:.2f}" if row.shipping_amount is not None else "n/a"
        match_line = ""
        if row.top_card_match_score is not None:
            match_line = (
                f"Top card: {row.top_card_name or 'n/a'} ({row.top_card_match_score:.0%})\n"
            )
        self._meta_label.setText(
            f"EV adj: {row.ev_adjusted:.2f}  |  EV raw: {row.ev_raw:.2f}\n"
            f"Confidence: {row.confidence_score:.2f}  |  Rank value: {row.rank_value:.2f}\n"
            f"Price: {row.price_amount:.2f} {row.currency}  + ship {ship}\n"
            f"{match_line}"
            f"Scoring: {row.scoring_version}"
        )
        self._fav_btn.setText("★ Favourited" if row.is_favorited else "☆ Favourite")
        self._fav_btn.setEnabled(True)
        self._open_ebay_btn.setEnabled(bool(row.listing_url))

        with self._session_factory() as session:
            note = fav.get_note(session, self._selected_id)
            detail = fetch_listing_detail(
                session,
                self._selected_id,
                image_cache_dir=self._settings.image_cache_dir,
            )
        self._note_edit.setText(note or "")
        self._detail_panel.set_detail(detail)

    def _toggle_favorite(self) -> None:
        if not self._selected_id:
            return
        row = self._row_for_id(str(self._selected_id))
        if not row:
            return
        with self._session_factory() as session:
            if row.is_favorited:
                fav.clear_favorite(session, self._selected_id)
            else:
                fav.set_favorite(session, self._selected_id, note=self._note_edit.text() or None)
        self.refresh()
        self._reselect(str(self._selected_id))

    def _save_note(self) -> None:
        if not self._selected_id:
            return
        with self._session_factory() as session:
            fav.set_favorite(session, self._selected_id, note=self._note_edit.text())

    def _reselect(self, listing_id: str) -> None:
        for r in range(self._model.rowCount()):
            idx = self._model.index(r, 0)
            if self._model.data(idx, Qt.ItemDataRole.UserRole) == listing_id:
                self._table.selectRow(r)
                self._on_selection_changed()
                break

    def _open_ebay(self) -> None:
        if not self._selected_id:
            return
        row = self._row_for_id(str(self._selected_id))
        if row and row.listing_url:
            QDesktopServices.openUrl(QUrl(row.listing_url))


class DatabaseTab(QWidget):
    def __init__(self, session_factory, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session_factory = session_factory
        self._headers: list[str] = []
        self._rows: list[tuple] = []

        layout = apply_tab_layout(self)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Query:"))
        self._query_combo = QComboBox()
        for q in CURATED_QUERIES:
            self._query_combo.addItem(q.label, q.query_id)
        toolbar.addWidget(self._query_combo, stretch=1)

        run_btn = QPushButton("Run")
        run_btn.setObjectName("primaryButton")
        run_btn.clicked.connect(self.run_query)
        toolbar.addWidget(run_btn)

        export_btn = QPushButton("Export CSV")
        export_btn.setObjectName("secondaryButton")
        export_btn.clicked.connect(self.export_csv)
        toolbar.addWidget(export_btn)
        layout.addLayout(toolbar)

        self._table = QTableView()
        self._model = GenericTableModel(self)
        self._table.setModel(self._model)
        self._table.setSortingEnabled(True)
        configure_data_table(self._table)
        layout.addWidget(self._table)

        self.run_query()

    def run_query(self) -> None:
        query_id = self._query_combo.currentData()
        try:
            with self._session_factory() as session:
                headers, rows = run_curated_query(str(query_id), session)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Query failed", str(exc))
            return
        self._headers = headers
        self._rows = rows
        self._model.set_data(headers, rows)

    def export_csv(self) -> None:
        if not self._headers:
            QMessageBox.information(self, "Export", "Run a query first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "query_export.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with Path(path).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(self._headers)
                writer.writerows(self._rows)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export", f"Saved to {path}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EbayWorkflows")
        self.resize(1200, 720)
        self.setMinimumSize(900, 500)

        try:
            settings = Settings()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(None, "Configuration error", str(exc))
            raise SystemExit(2) from exc

        self._settings = settings
        self._session_factory = build_session_factory(settings)

        self._poll_warning = QLabel("")
        self._poll_warning.setObjectName("pollWarning")
        self.statusBar().addWidget(self._poll_warning)

        self._poll_reporter = GuiPollErrorReporter(on_message=self._set_poll_warning)

        self._job_runner = JobRunner(self)

        tabs = QTabWidget()
        tabs.setObjectName("mainTabs")
        self._tabs = tabs
        self._dashboard = DashboardTab(
            self._session_factory,
            self._job_runner,
            settings,
            poll_reporter=self._poll_reporter,
        )
        tabs.addTab(self._dashboard, "Home")
        self._opportunities = OpportunitiesTab(settings, self._session_factory)
        tabs.addTab(self._opportunities, "Opportunities")
        self._workflows = WorkflowsTab(
            settings,
            self._session_factory,
            self._job_runner,
            on_ranking_refresh=self._opportunities.refresh,
            poll_reporter=self._poll_reporter,
        )
        tabs.addTab(self._workflows, "Workflows")
        tabs.addTab(DatabaseTab(self._session_factory), "Database")
        self._dashboard.navigate_to_workflows.connect(
            lambda: tabs.setCurrentWidget(self._workflows)
        )
        self._workflows._stale_panel.changed.connect(self._dashboard.refresh)
        self.setCentralWidget(tabs)

        view_menu = self.menuBar().addMenu("View")
        self._dark_mode_action = QAction("Dark theme", self)
        self._dark_mode_action.setCheckable(True)
        from .theme import is_dark_mode_enabled, toggle_dark_mode

        self._dark_mode_action.setChecked(is_dark_mode_enabled())
        self._dark_mode_action.triggered.connect(lambda _: toggle_dark_mode(QApplication.instance()))
        view_menu.addAction(self._dark_mode_action)

        self._status = QLabel("")
        self.statusBar().addPermanentWidget(self._status, stretch=1)
        self._status_poll = QTimer(self)
        self._status_poll.setInterval(2000)
        self._status_poll.timeout.connect(self._update_status)
        self._status_poll.start()
        self._opportunities.refresh()
        self._update_status()

    def _set_poll_warning(self, message: str | None) -> None:
        self._poll_warning.setText(message or "")

    def _update_status(self) -> None:
        count = len(self._opportunities._rows)
        parts = [
            f"Listings shown: {count}",
            f"Cache: {self._settings.image_cache_dir}",
        ]
        try:
            with self._session_factory() as session:
                stats = fetch_dashboard_stats(session)
                parts.insert(0, f"DB: {stats.listing_count:,} listings · {stats.ranked_count:,} ranked")
                match = collect_match_stats(session)
                if match.get("verified_listings", 0) > 0:
                    parts.insert(1, f"Verified: {match['verified_listings']:,}")
                if stats.running_count:
                    running = fetch_running_workflows(session)
                    if running:
                        active = running[0]
                        progress = resolve_progress(session, active)
                        elapsed = elapsed_label(active.step)
                        label = WORKFLOW_JOBS.get(active.job_id)
                        name = label.label if label else active.job_id
                        if progress:
                            pct = progress.percent
                            prog = f"{progress.current:,}/{progress.total:,} {progress.unit}"
                            if pct is not None:
                                prog = f"{pct}% ({prog})"
                        else:
                            prog = "starting…"
                        parts.append(f"Running: {name} {prog} · {elapsed}")
            if self._poll_reporter is not None:
                self._poll_reporter.report_success()
        except Exception as exc:  # noqa: BLE001
            handle_poll_error(self._poll_reporter, exc, context="Status bar")
        if self._job_runner.is_busy():
            job = self._job_runner.current_job_id or "job"
            state = "paused" if self._job_runner.is_paused() else "running"
            parts.append(f"GUI process: {job} ({state})")
        self._status.setText("  |  ".join(parts))


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("EbayWorkflows")
    from .theme import apply_app_theme

    apply_app_theme(app)

    from ..logging_config import configure_logging

    try:
        configure_logging(Settings().log_level)
    except Exception:  # noqa: BLE001
        configure_logging("info")

    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
