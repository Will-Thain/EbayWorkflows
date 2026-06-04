from __future__ import annotations

import csv
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QStyleFactory,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from ..config import Settings
from ..db import build_session_factory
from ..models import ListingImage
from ..services.ranked_export import RankedListingRow, fetch_ranked_listings
from . import favorites as fav
from .db_browser import CURATED_QUERIES, run_curated_query
from .models_qt import GenericTableModel, RankedListTableModel
from .presenters import is_safe_cache_path


class OpportunitiesTab(QWidget):
    def __init__(self, settings: Settings, session_factory, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._session_factory = session_factory
        self._rows: list[RankedListingRow] = []
        self._selected_id: uuid.UUID | None = None

        layout = QVBoxLayout(self)

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
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(refresh_btn)

        self._open_ebay_btn = QPushButton("Open on eBay")
        self._open_ebay_btn.clicked.connect(self._open_ebay)
        self._open_ebay_btn.setEnabled(False)
        toolbar.addWidget(self._open_ebay_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._table = QTableView()
        self._model = RankedListTableModel(self)
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._table)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)

        self._title_label = QLabel("Select a listing")
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        detail_layout.addWidget(self._title_label)

        self._meta_label = QLabel("")
        self._meta_label.setWordWrap(True)
        detail_layout.addWidget(self._meta_label)

        fav_box = QGroupBox("Favourite")
        fav_form = QFormLayout(fav_box)
        self._fav_btn = QPushButton("☆ Favourite")
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

        self._image_label = QLabel("No image")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumHeight(280)
        self._image_label.setStyleSheet("background: palette(mid); border: 1px solid palette(midlight);")
        detail_layout.addWidget(self._image_label, stretch=1)

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
        self._image_label.setText("No image")
        self._image_label.setPixmap(QPixmap())
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
        self._note_edit.setText(note or "")

        self._show_image(self._selected_id)

    def _show_image(self, listing_id: uuid.UUID) -> None:
        with self._session_factory() as session:
            images = (
                session.execute(
                    select(ListingImage)
                    .where(
                        ListingImage.listing_id == listing_id,
                        ListingImage.download_status == "succeeded",
                    )
                    .limit(5)
                )
                .scalars()
                .all()
            )

        path = None
        for img in images:
            if is_safe_cache_path(img.local_path, self._settings.image_cache_dir):
                path = img.local_path
                break

        if not path:
            self._image_label.setPixmap(QPixmap())
            self._image_label.setText("No cached image")
            return

        pixmap = QPixmap(path)
        if pixmap.isNull():
            self._image_label.setPixmap(QPixmap())
            self._image_label.setText("Could not load image")
            return

        scaled = pixmap.scaled(
            self._image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setText("")
        self._image_label.setPixmap(scaled)

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

        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Query:"))
        self._query_combo = QComboBox()
        for q in CURATED_QUERIES:
            self._query_combo.addItem(q.label, q.query_id)
        toolbar.addWidget(self._query_combo, stretch=1)

        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self.run_query)
        toolbar.addWidget(run_btn)

        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self.export_csv)
        toolbar.addWidget(export_btn)
        layout.addLayout(toolbar)

        self._table = QTableView()
        self._model = GenericTableModel(self)
        self._table.setModel(self._model)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setStretchLastSection(True)
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


class PlaceholderTab(QWidget):
    def __init__(self, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel(message)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


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

        tabs = QTabWidget()
        self._opportunities = OpportunitiesTab(settings, self._session_factory)
        tabs.addTab(self._opportunities, "Opportunities")
        tabs.addTab(
            PlaceholderTab("Workflows (start/stop, logs, schedules) — planned in GUI-2 / GUI-6."),
            "Workflows",
        )
        tabs.addTab(DatabaseTab(self._session_factory), "Database")
        self.setCentralWidget(tabs)

        self._status = QLabel("")
        self.statusBar().addPermanentWidget(self._status, stretch=1)
        self._opportunities.refresh()
        self._update_status()

    def _update_status(self) -> None:
        count = len(self._opportunities._rows)
        self._status.setText(
            f"Listings shown: {count}  |  Image cache: {self._settings.image_cache_dir}"
        )


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("EbayWorkflows")
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
