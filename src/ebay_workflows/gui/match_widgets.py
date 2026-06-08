from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .listing_detail import DetectionDetail, ListingDetail, ListingImageDetail, MatchDetail, detection_for_match


class BboxImageWidget(QLabel):
    """Listing image with optional normalized bounding-box overlays."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(240)
        self.setStyleSheet("background: palette(mid); border: 1px solid palette(midlight);")
        self._source: QPixmap | None = None
        self._bboxes: list[tuple[float, float, float, float]] = []
        self._highlight: int | None = None
        self._draw_rect = (0, 0, 0, 0)

    def set_image(
        self,
        path: str | None,
        detections: list[DetectionDetail] | None = None,
        *,
        highlight_index: int | None = None,
    ) -> None:
        self._highlight = highlight_index
        self._bboxes = []
        if detections:
            self._bboxes = [(d.bbox_x, d.bbox_y, d.bbox_w, d.bbox_h) for d in detections]

        if not path:
            self._source = None
            self.setText("No cached image")
            self.update()
            return

        pixmap = QPixmap(path)
        if pixmap.isNull():
            self._source = None
            self.setText("Could not load image")
            self.update()
            return

        self._source = pixmap
        self.setText("")
        self._rescale()
        self.update()

    def set_highlight(self, index: int | None) -> None:
        self._highlight = index
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        super().resizeEvent(event)
        self._rescale()
        self.update()

    def _rescale(self) -> None:
        if self._source is None or self._source.isNull():
            self._draw_rect = (0, 0, 0, 0)
            return
        scaled = self._source.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self._draw_rect = (x, y, scaled.width(), scaled.height())

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._source is None or self._source.isNull():
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x, y, w, h = self._draw_rect
        scaled = self._source.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(x, y, scaled)

        for idx, (bx, by, bw, bh) in enumerate(self._bboxes):
            rx = x + int(bx * w)
            ry = y + int(by * h)
            rw = max(2, int(bw * w))
            rh = max(2, int(bh * h))
            is_hi = idx == self._highlight
            color = QColor(0, 200, 80) if is_hi else QColor(255, 180, 0)
            painter.setPen(QPen(color, 4 if is_hi else 2))
            painter.drawRect(rx, ry, rw, rh)
            if is_hi:
                painter.fillRect(rx, ry, rw, rh, QColor(0, 200, 80, 50))
                painter.setPen(QPen(color, 2))
                painter.drawText(rx + 4, ry + 18, f"Match #{idx + 1}")


class ImageGalleryBar(QWidget):
    image_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._images: list[ListingImageDetail] = []
        self._index = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedWidth(36)
        self._prev_btn.clicked.connect(self._prev)
        layout.addWidget(self._prev_btn)

        self._label = QLabel("No images")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label, stretch=1)

        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedWidth(36)
        self._next_btn.clicked.connect(self._next)
        layout.addWidget(self._next_btn)

    def set_images(self, images: list[ListingImageDetail]) -> None:
        self._images = images
        self._index = 0
        self._sync()

    def current_image(self) -> ListingImageDetail | None:
        if not self._images:
            return None
        return self._images[self._index]

    def _sync(self) -> None:
        has = bool(self._images)
        self._prev_btn.setEnabled(has and self._index > 0)
        self._next_btn.setEnabled(has and self._index < len(self._images) - 1)
        if not has:
            self._label.setText("No images")
        else:
            self._label.setText(f"Image {self._index + 1} of {len(self._images)}")
        self.image_changed.emit(self._index)

    def _prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._sync()

    def _next(self) -> None:
        if self._index < len(self._images) - 1:
            self._index += 1
            self._sync()


class MatchRowWidget(QWidget):
    expanded = Signal(int)

    def __init__(self, match: MatchDetail, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._match = match

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)

        price = "—"
        if match.price_amount is not None:
            cur = match.price_currency or "EUR"
            price = f"{match.price_amount:.2f} {cur}"

        header = QPushButton(
            f"#{match.rank_position}  {match.card_name or 'Unknown'}  "
            f"|  Match {match.match_score:.0%}  |  {price}"
        )
        header.setCheckable(True)
        header.setChecked(False)
        header.setStyleSheet("text-align: left; font-weight: bold;")
        header.clicked.connect(self._toggle)
        layout.addWidget(header)
        self._header = header

        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(12, 4, 4, 4)

        meta_lines = [
            f"Confidence: {match.confidence_score:.0%}",
            f"Set: {match.set_code or 'n/a'}",
        ]
        if match.price_type:
            meta_lines.append(f"Price type: {match.price_type}")
        if not match.pricing_eligible and match.pricing_reject_reason:
            meta_lines.append(f"Pricing: excluded ({match.pricing_reject_reason})")
        if match.ocr_title:
            ocr_line = f"OCR: {match.ocr_title}"
            if match.ocr_similarity is not None:
                ocr_line += f" ({match.ocr_similarity:.0%})"
            meta_lines.append(ocr_line)
        if match.embedding_agreement is True:
            meta_lines.append("Embedding: agrees with title match")
        elif match.embedding_agreement is False:
            meta_lines.append("Embedding: disagrees with title match")

        for line in meta_lines:
            body_layout.addWidget(QLabel(line))

        if match.faiss_matches:
            body_layout.addWidget(QLabel("Visual matches (FAISS):"))
            for idx, fm in enumerate(match.faiss_matches[:5], start=1):
                name = fm.card_name or fm.scryfall_id
                body_layout.addWidget(QLabel(f"  {idx}. {name} ({fm.score:.0%})"))

        self._crop_label = QLabel()
        self._crop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._crop_label.setMaximumHeight(160)
        body_layout.addWidget(self._crop_label)

        self._body.setVisible(False)
        layout.addWidget(self._body)

    def match(self) -> MatchDetail:
        return self._match

    def set_crop_path(self, path: str | None) -> None:
        if not path:
            self._crop_label.clear()
            self._crop_label.setText("")
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self._crop_label.setText("Crop unavailable")
            return
        scaled = pixmap.scaled(
            self._crop_label.size().boundedTo(pixmap.size()),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._crop_label.setPixmap(scaled)

    def _toggle(self) -> None:
        expanded = self._header.isChecked()
        self._body.setVisible(expanded)
        if expanded:
            self.expanded.emit(self._match.rank_position)


class MatchListPanel(QWidget):
    match_selected = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[MatchRowWidget] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(QLabel("Card matches (rank order)"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.addStretch()
        scroll.setWidget(self._container)
        outer.addWidget(scroll)

    def set_matches(self, matches: list[MatchDetail]) -> None:
        while self._container_layout.count() > 1:
            item = self._container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()

        if not matches:
            empty = QLabel("No card matches for this listing.")
            self._container_layout.insertWidget(0, empty)
            return

        for match in matches:
            row = MatchRowWidget(match)
            row.expanded.connect(self._on_expanded)
            self._container_layout.insertWidget(self._container_layout.count() - 1, row)
            self._rows.append(row)

    def set_crop_for_match(self, rank_position: int, path: str | None) -> None:
        for row in self._rows:
            if row.match().rank_position == rank_position:
                row.set_crop_path(path)
                break

    def _on_expanded(self, rank_position: int) -> None:
        for row in self._rows:
            if row.match().rank_position != rank_position:
                row._header.setChecked(False)
                row._body.setVisible(False)
        self.match_selected.emit(rank_position)


class ListingDetailPanel(QWidget):
    """Image gallery + bbox preview + expandable rank-ordered matches."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._detail: ListingDetail | None = None
        self._highlight: int | None = None

        layout = QVBoxLayout(self)
        self._gallery = ImageGalleryBar()
        self._gallery.image_changed.connect(self._on_image_changed)
        layout.addWidget(self._gallery)

        self._image = BboxImageWidget()
        self._image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._image, stretch=2)

        self._match_panel = MatchListPanel()
        self._match_panel.match_selected.connect(self._on_match_selected)
        layout.addWidget(self._match_panel, stretch=3)

    def set_detail(self, detail: ListingDetail | None) -> None:
        self._detail = detail
        self._highlight = None
        if not detail:
            self._gallery.set_images([])
            self._image.set_image(None)
            self._match_panel.set_matches([])
            return

        self._gallery.set_images(detail.images)
        self._match_panel.set_matches(detail.matches)
        self._refresh_image()

    def _current_image(self) -> ListingImageDetail | None:
        return self._gallery.current_image()

    def _refresh_image(self) -> None:
        img = self._current_image()
        if not img:
            self._image.set_image(None)
            return
        self._image.set_image(img.local_path, img.detections, highlight_index=self._highlight)

    def _on_image_changed(self, _index: int) -> None:
        self._highlight = None
        self._refresh_image()

    def _on_match_selected(self, rank_position: int) -> None:
        if not self._detail:
            return
        match = next((m for m in self._detail.matches if m.rank_position == rank_position), None)
        img = self._current_image()
        if not match or not img:
            return

        det_idx = detection_for_match(img.detections, match)
        self._highlight = det_idx
        self._refresh_image()

        crop_path: str | None = None
        if det_idx is not None and 0 <= det_idx < len(img.detections):
            crop_path = img.detections[det_idx].crop_path
        self._match_panel.set_crop_for_match(rank_position, crop_path)
