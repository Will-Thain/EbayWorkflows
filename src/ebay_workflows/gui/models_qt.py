from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from ..services.ranked_export import RankedListingRow
from .presenters import truncate_title


class GenericTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._headers: list[str] = []
        self._rows: list[tuple[Any, ...]] = []

    def set_data(self, headers: list[str], rows: list[tuple[Any, ...]]) -> None:
        self.beginResetModel()
        self._headers = headers
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        value = self._rows[index.row()][index.column()]
        if value is None:
            return ""
        return str(value)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        if 0 <= section < len(self._headers):
            return self._headers[section]
        return None


class RankedListTableModel(QAbstractTableModel):
    HEADERS = ("Rank", "EV adj", "Conf", "Title", "Top card", "★", "Price")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[RankedListingRow] = []

    def set_rows(self, rows: list[RankedListingRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_at(self, index: QModelIndex) -> RankedListingRow | None:
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._rows):
            return None
        return self._rows[index.row()]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        row = self.row_at(index)
        if row is None:
            return None
        if role == Qt.ItemDataRole.UserRole:
            return row.listing_id
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        col = index.column()
        if col == 0:
            return str(row.rank)
        if col == 1:
            return f"{row.ev_adjusted:.2f}"
        if col == 2:
            return f"{row.confidence_score:.2f}"
        if col == 3:
            return truncate_title(row.title)
        if col == 4:
            return row.top_card_name or ""
        if col == 5:
            return "★" if row.is_favorited else ""
        if col == 6:
            return f"{row.price_amount:.2f} {row.currency}"
        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        if 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return None
