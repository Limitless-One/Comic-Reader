from __future__ import annotations
from typing import List, TYPE_CHECKING

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt5.QtGui import QResizeEvent, QPixmap, QWheelEvent, QIcon
from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea,
    QComboBox, QToolButton, QFrame, QSpinBox, QSizePolicy
)

from models.comic_model import ChapterState
from utils.archive_handler import get_page_refs, PageRef
from utils.config import READER_SCROLL_STEP

if TYPE_CHECKING:
    from controllers.comic_controller import ComicController


class ReaderView(QWidget):
    back_to_chapters = pyqtSignal()
    chapter_requested = pyqtSignal(str)
    page_changed = pyqtSignal(int)

    _ZOOM_LEVELS = [0.25, 0.50, 0.75, 0.85, 1.0, 1.25, 1.50, 2.0]
    _DEFAULT_ZOOM_INDEX = 2

    def __init__(self, controller: "ComicController") -> None:
        super().__init__()
        self.controller = controller
        self._is_dark = False

        self._page_refs: List[PageRef] = []
        self._page_labels: List[QLabel] = []
        self._current_key: str | None = None
        self._chapter_keys: List[str] = []
        self._zoom_index = self._DEFAULT_ZOOM_INDEX
        self._last_rendered_width = 0
        self._current_page_index = 0

        self._setup_ui()
        self.apply_settings()

    def _setup_ui(self):
        self.back_btn = QPushButton("← Chapters")
        self.chapter_box = QComboBox()

        self.page_spinbox = QSpinBox()
        self.page_spinbox.setPrefix("Page ")
        self.page_spinbox.valueChanged.connect(self._jump_to_page)
        self.page_label = QLabel("/ 1")

        self.prev_btn = QToolButton(text="◀")
        self.next_btn = QToolButton(text="▶")

        self.mode_btn = QPushButton("Single Page")
        self.mode_btn.setCheckable(True)

        self.zoom_out_btn = QToolButton(text="-")
        self.zoom_in_btn = QToolButton(text="+")
        self.zoom_label = QLabel()
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setMinimumWidth(50)

        self.back_btn.clicked.connect(self.back_to_chapters.emit)
        self.chapter_box.currentIndexChanged.connect(self._on_dropdown_change)
        self.prev_btn.clicked.connect(lambda: self._navigate(-1))
        self.next_btn.clicked.connect(lambda: self._navigate(+1))
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        self.mode_btn.toggled.connect(self._toggle_mode)

        zoom_layout = QHBoxLayout()
        zoom_layout.setSpacing(0)
        zoom_layout.addWidget(self.zoom_out_btn)
        zoom_layout.addWidget(self.zoom_label)
        zoom_layout.addWidget(self.zoom_in_btn)

        page_nav_layout = QHBoxLayout()
        page_nav_layout.setSpacing(5)
        page_nav_layout.addWidget(self.page_spinbox)
        page_nav_layout.addWidget(self.page_label)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self.back_btn)
        top_bar.addWidget(self.prev_btn)
        top_bar.addWidget(self.chapter_box, 1)
        top_bar.addWidget(self.next_btn)
        top_bar.addLayout(page_nav_layout)
        top_bar.addWidget(self.mode_btn)
        top_bar.addStretch(2)
        top_bar.addLayout(zoom_layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.vbox.setSpacing(4)
        self.scroll.setWidget(self.container)

        self._setup_floating_nav()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addLayout(top_bar)
        root.addWidget(self.scroll)
        self.setFocusPolicy(Qt.StrongFocus)

    def _setup_floating_nav(self):
        # CORRECTION 2: Use QHBoxLayout for horizontal button layout.
        self.nav_widget = QWidget(self.scroll)
        nav_layout = QHBoxLayout(self.nav_widget)
        nav_layout.setContentsMargins(4, 4, 4, 4)
        nav_layout.setSpacing(8)

        self.scroll_top_btn = QToolButton(text="▲")
        self.scroll_bottom_btn = QToolButton(text="▼")
        self.scroll_top_btn.clicked.connect(lambda: self.scroll.verticalScrollBar().setValue(0))
        self.scroll_bottom_btn.clicked.connect(
            lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

        nav_layout.addWidget(self.scroll_top_btn)
        nav_layout.addWidget(self.scroll_bottom_btn)
        self.nav_widget.hide()

        self._nav_fade_timer = QTimer(self)
        self._nav_fade_timer.setSingleShot(True)
        self._nav_fade_timer.timeout.connect(self.nav_widget.hide)
        self.scroll.verticalScrollBar().valueChanged.connect(self._show_floating_nav)

    def _show_floating_nav(self):
        if not self.nav_widget.isVisible():
            self.nav_widget.show()
        self.nav_widget.raise_()
        self._nav_fade_timer.start(2000)

    def apply_settings(self):
        default_zoom = self.controller.settings.value(
            self.controller.SETTINGS_DEFAULT_ZOOM, self._DEFAULT_ZOOM_INDEX, type=int
        )
        self._zoom_index = default_zoom
        self._update_zoom_label()

    def reset_zoom_to_default(self):
        self.apply_settings()

    def load_chapter(self, chapter: ChapterState, chapter_order: List[ChapterState], start_page: int = 0):
        self._current_key = chapter.path.name
        self._chapter_keys = [c.path.name for c in chapter_order]

        self.chapter_box.blockSignals(True)
        self.chapter_box.clear()
        for ch in chapter_order:
            self.chapter_box.addItem(ch.display_name, ch.path.name)
        idx = self.chapter_box.findData(self._current_key)
        self.chapter_box.setCurrentIndex(max(0, idx))
        self.chapter_box.blockSignals(False)

        self._page_refs = get_page_refs(chapter.path)
        self._update_page_nav_ui()
        self._render_layout(start_page)

    def _render_layout(self, start_page: int = 0):
        while self.vbox.count():
            child = self.vbox.takeAt(0)
            if child and child.widget():
                child.widget().deleteLater()
        self._page_labels.clear()

        if not self._page_refs: return

        for _ in self._page_refs:
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignCenter)
            self.vbox.addWidget(lbl)
            self._page_labels.append(lbl)

        self.page_spinbox.blockSignals(True)
        self.page_spinbox.setValue(start_page + 1)
        self.page_spinbox.blockSignals(False)
        self._current_page_index = start_page

        self._last_rendered_width = 0
        QTimer.singleShot(50, lambda: self._initial_scroll(start_page))

    def _initial_scroll(self, page_index: int):
        self._scale_and_load_visible_pages()
        if self.mode_btn.isChecked():
            self._render_single_page()
        elif page_index > 0 and page_index < len(self._page_labels):
            target_label = self._page_labels[page_index]
            self.scroll.ensureWidgetVisible(target_label)

    def _scale_and_load_visible_pages(self):
        viewport_height = self.scroll.viewport().height()
        viewport_y_pos = self.scroll.verticalScrollBar().value()
        available_width = self.scroll.viewport().width() - 20
        zoom_factor = self._ZOOM_LEVELS[self._zoom_index]
        target_width = int(available_width * zoom_factor)

        if target_width <= 0: return

        width_changed = self._last_rendered_width != target_width
        self._last_rendered_width = target_width
        top_visible_page = -1

        for i, (ref, label) in enumerate(zip(self._page_refs, self._page_labels)):
            if width_changed or not label.pixmap():
                pixmap = ref.get_pixmap()
                if pixmap:
                    scaled_pixmap = pixmap.scaledToWidth(target_width, Qt.SmoothTransformation)
                    label.setPixmap(scaled_pixmap)

            if not self.mode_btn.isChecked():
                label_y_pos = label.y()
                is_visible = (label_y_pos < viewport_y_pos + viewport_height and
                              label_y_pos + label.height() > viewport_y_pos)

                if is_visible and top_visible_page == -1:
                    top_visible_page = i

        if top_visible_page != -1:
            self._current_page_index = top_visible_page

        if self._current_page_index + 1 != self.page_spinbox.value():
            self.page_spinbox.blockSignals(True)
            self.page_spinbox.setValue(self._current_page_index + 1)
            self.page_spinbox.blockSignals(False)

        self.page_changed.emit(self._current_page_index)

    def _on_dropdown_change(self, i: int):
        key = self.chapter_box.itemData(i)
        if key and key != self._current_key:
            self.chapter_requested.emit(key)

    def _navigate(self, delta: int):
        if not self._current_key or not self._chapter_keys: return

        if self.mode_btn.isChecked() and len(self._page_refs) > 0:
            new_page = self._current_page_index + delta
            if 0 <= new_page < len(self._page_refs):
                self._current_page_index = new_page
                self._render_single_page()
            elif new_page >= len(self._page_refs):
                self._navigate_chapter(1)
            elif new_page < 0:
                self._navigate_chapter(-1, go_to_last_page=True)
        else:
            self._navigate_chapter(delta)

    def _navigate_chapter(self, delta: int, go_to_last_page: bool = False):
        if self._current_key not in self._chapter_keys: return
        current_idx = self._chapter_keys.index(self._current_key)
        new_idx = (current_idx + delta) % len(self._chapter_keys)
        self.chapter_requested.emit(self._chapter_keys[new_idx])

    def _toggle_mode(self, is_single_page: bool):
        self.mode_btn.setText("Single Page" if is_single_page else "Continuous")
        self.page_spinbox.setVisible(is_single_page)
        self.page_label.setVisible(is_single_page)
        if is_single_page:
            self._render_single_page()
        else:
            self._render_layout(self._current_page_index)

    def _render_single_page(self):
        for i, label in enumerate(self._page_labels):
            label.setVisible(i == self._current_page_index)
        self._scale_and_load_visible_pages()
        if 0 <= self._current_page_index < len(self._page_labels):
            self.scroll.verticalScrollBar().setValue(0)
            self.scroll.ensureWidgetVisible(self._page_labels[self._current_page_index])

    def _jump_to_page(self, page_num: int):
        target_index = page_num - 1
        if 0 <= target_index < len(self._page_refs):
            self._current_page_index = target_index
            if self.mode_btn.isChecked():
                self._render_single_page()
            elif self._current_page_index < len(self._page_labels):
                self.scroll.ensureWidgetVisible(self._page_labels[self._current_page_index])

    def _update_page_nav_ui(self):
        num_pages = len(self._page_refs)
        self.page_spinbox.setVisible(self.mode_btn.isChecked())
        self.page_label.setVisible(self.mode_btn.isChecked())
        if num_pages > 0:
            self.page_spinbox.setRange(1, num_pages)
            self.page_label.setText(f"/ {num_pages}")
        else:
            self.page_spinbox.setRange(1, 1)
            self.page_label.setText("/ 1")

    def _update_zoom_label(self):
        zoom_percent = int(self._ZOOM_LEVELS[self._zoom_index] * 100)
        self.zoom_label.setText(f"{zoom_percent}%")

    def _zoom(self, delta: int):
        new_index = self._zoom_index + delta
        if 0 <= new_index < len(self._ZOOM_LEVELS):
            self._zoom_index = new_index
            self._update_zoom_label()
            self._last_rendered_width = 0
            self._scale_and_load_visible_pages()

    def _zoom_in(self):
        self._zoom(1)

    def _zoom_out(self):
        self._zoom(-1)

    def set_dark_mode(self, is_dark: bool):
        self._is_dark = is_dark
        bg_color = "#1e1e1e" if is_dark else "#dddddd"
        self.container.setStyleSheet(f"background-color: {bg_color};")

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.nav_widget.move(self.scroll.width() - self.nav_widget.width() - 10,
                             self.scroll.height() - self.nav_widget.height() - 10)
        if not hasattr(self, '_resize_timer'):
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._scale_and_load_visible_pages)
        self._resize_timer.start(50)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.ControlModifier:
            delta = 1 if event.angleDelta().y() > 0 else -1
            self._zoom(delta)
        else:
            self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().value() - event.angleDelta().y() // 2
            )

    def showEvent(self, event):
        super().showEvent(event)
        self.scroll.verticalScrollBar().valueChanged.connect(self._scale_and_load_visible_pages)

    def hideEvent(self, event):
        super().hideEvent(event)
        try:
            self.scroll.verticalScrollBar().valueChanged.disconnect(self._scale_and_load_visible_pages)
        except TypeError:
            pass

    def keyPressEvent(self, e):
        scroll_bar = self.scroll.verticalScrollBar()
        if e.key() in (Qt.Key_Left, Qt.Key_PageUp):
            self._navigate(-1)
        elif e.key() in (Qt.Key_Right, Qt.Key_PageDown):
            self._navigate(+1)
        elif e.key() == Qt.Key_Down:
            scroll_bar.setValue(scroll_bar.value() + READER_SCROLL_STEP)
        elif e.key() == Qt.Key_Up:
            scroll_bar.setValue(scroll_bar.value() - READER_SCROLL_STEP)
        elif e.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self._zoom_in()
        elif e.key() == Qt.Key_Minus:
            self._zoom_out()
        else:
            super().keyPressEvent(e)

