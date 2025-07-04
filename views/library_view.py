from __future__ import annotations

"""LibraryView
===============
Main comics library UI pane with grid/list toggle, folder navigation,
search bar with live filtering, and a favorites-only view toggle.
"""

import re
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt, QSize, pyqtSignal, QEvent
from PyQt5.QtGui import QIcon, QPixmap, QFontMetrics, QCursor
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QToolButton,
    QHBoxLayout,
    QVBoxLayout,
    QSizePolicy,
    QGridLayout,
    QScrollArea,
    QFrame,
    QStyle,
    QLineEdit,
)

from utils import get_first_page_preview

# ---------------------------------------------------------------------------
# Constants
_THUMB_BOX = QSize(180, 250)
_PREVIEW_MAX = (140, 180)
_MIN_CELL_SPACING = 20
_MAX_CELL_SPACING = 40


def _natural_key(text: str):
    parts = re.split(r"(\d+(?:\.\d+)?)", str(text))
    key: list[tuple[int, object]] = []
    for p in parts:
        if not p:
            continue
        key.append((0, float(p)) if p.replace(".", "", 1).isdigit() else (1, p.lower()))
    return key


# ---------------------------------------------------------------------------
# Helper item widgets
class _GridItem(QWidget):
    def __init__(
            self,
            name: str,
            preview: Optional[QPixmap],
            is_comic: bool,
            icon_folder: QIcon,
            icon_comic: QIcon,
            click_handler,
            favorite: bool = False,
            toggle_fav_handler=None,
    ) -> None:
        super().__init__()
        self.setFixedSize(_THUMB_BOX)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._name = name
        self._toggle_fav_handler = toggle_fav_handler

        outer = QWidget(self)
        outer.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border-radius: 16px;
                border: 1px solid #444;
            }
        """)
        outer.setGeometry(0, 0, _THUMB_BOX.width(), _THUMB_BOX.height())

        lay = QVBoxLayout(outer)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(16)

        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        img_lbl = QLabel()
        img_lbl.setFixedSize(*_PREVIEW_MAX)
        img_lbl.setAlignment(Qt.AlignCenter)
        img_lbl.setStyleSheet("border-radius: 10px; background-color: #888;")

        if preview and not preview.isNull():
            img_lbl.setPixmap(
                preview.scaled(img_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            fallback = icon_comic if is_comic else icon_folder
            img_lbl.setPixmap(fallback.pixmap(64, 64))

        preview_layout.addWidget(img_lbl)

        if is_comic:
            self.fav_btn = QToolButton(img_lbl)
            self.fav_btn.setText("★")
            self.fav_btn.setCheckable(True)
            self.fav_btn.setChecked(favorite)
            self.fav_btn.setCursor(QCursor(Qt.PointingHandCursor))
            self.fav_btn.setFixedSize(24, 24)
            self.fav_btn.move(img_lbl.width() - 28, img_lbl.height() - 28)

            def toggle_color():
                self.update_fav_color()
                if self._toggle_fav_handler:
                    self._toggle_fav_handler()

            self.update_fav_color()
            self.fav_btn.clicked.connect(toggle_color)
        else:
            self.fav_btn = None

        fm = QFontMetrics(self.font())
        elided = fm.elidedText(name, Qt.ElideRight, _PREVIEW_MAX[0])

        title_btn = QPushButton(elided)
        title_btn.setToolTip(name)
        title_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: #fff;
                border-radius: 6px;
                padding: 4px 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        title_btn.setFixedWidth(_PREVIEW_MAX[0])
        title_btn.clicked.connect(click_handler)

        lay.addWidget(preview_container, alignment=Qt.AlignCenter)
        lay.addWidget(title_btn, alignment=Qt.AlignCenter)

    def update_fav_color(self):
        if self.fav_btn:
            self.fav_btn.setStyleSheet(f"""
                QToolButton {{
                    background-color: transparent;
                    border: none;
                    font-size: 16px;
                    color: {'#FFD700' if self.fav_btn.isChecked() else '#999999'};
                }}
                QToolButton:hover {{
                    color: #FFD700;
                }}
            """)

    def set_favorite(self, favorite: bool):
        if self.fav_btn:
            self.fav_btn.setChecked(favorite)
            self.update_fav_color()


class _ListItem(QWidget):
    _HEIGHT = 44

    def __init__(
            self,
            name: str,
            is_comic: bool,
            icon_folder: QIcon,
            icon_comic: QIcon,
    ) -> None:
        super().__init__()
        self.setFixedHeight(self._HEIGHT)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap((icon_comic if is_comic else icon_folder).pixmap(24, 24))

        txt = QLabel(name)
        txt.setStyleSheet("color:#ffffff;")
        txt.setToolTip(name)
        txt.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        lay.addWidget(icon_lbl)
        lay.addWidget(txt)
        lay.addStretch(1)

        self.mouseReleaseEvent = lambda e: None


# ---------------------------------------------------------------------------
class LibraryView(QWidget):
    folder_selected = pyqtSignal(str)
    comic_selected = pyqtSignal(str)
    back_requested = pyqtSignal()
    root_change_requested = pyqtSignal()
    favorite_toggled = pyqtSignal(str)

    def __init__(self, controller=None) -> None:
        super().__init__()
        self._controller = controller
        self._grid_mode = True
        self._search_text = ""
        self._show_favorites_only = False
        self._grid_items = {}

        self.path_label = QLabel("/")

        up_btn = QPushButton("← Up")
        up_btn.clicked.connect(self.back_requested.emit)

        self.change_btn = QPushButton("Change Folder…")
        self.change_btn.clicked.connect(self.root_change_requested.emit)

        self.toggle_btn = QToolButton()
        self.toggle_btn.setText("📂")
        self.toggle_btn.setToolTip("Toggle view mode")
        self.toggle_btn.clicked.connect(self._toggle_view)

        self.fav_btn = QToolButton()
        self.fav_btn.setText("★")
        self.fav_btn.setToolTip("Toggle favorites view")
        self.fav_btn.setCheckable(True)
        self.fav_btn.toggled.connect(self._toggle_favorites_view)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍Search")
        self.search_box.textChanged.connect(self._live_filter)
        self.search_box.returnPressed.connect(self._apply_search)

        bar = QHBoxLayout()
        bar.addWidget(up_btn)
        bar.addWidget(self.search_box, stretch=2)
        bar.addWidget(self.path_label, stretch=1)
        bar.addWidget(self.fav_btn)
        bar.addWidget(self.toggle_btn)
        bar.addWidget(self.change_btn)

        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(_MIN_CELL_SPACING)
        self._grid.setContentsMargins(_MIN_CELL_SPACING, _MIN_CELL_SPACING, _MIN_CELL_SPACING, _MIN_CELL_SPACING)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self._container)

        # ✨ Empty label when no favorites
        self._empty_label = QLabel("No Favorites Yet!")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet("color: #aaa; font-size: 16px; padding: 40px;")
        self._empty_label.hide()

        outer = QVBoxLayout(self)
        outer.addLayout(bar)
        outer.addWidget(self.scroll)
        outer.addWidget(self._empty_label)

        style = QApplication.style()
        self._icon_folder = style.standardIcon(QStyle.SP_DirIcon)
        self._icon_comic = style.standardIcon(QStyle.SP_FileIcon)

        self._root: Optional[Path] = None
        self._rel = ""
        self._folders: List[str] = []
        self._comics: List[str] = []

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._root is not None and self._grid_mode:
            self.populate(self._rel, self._folders, self._comics, self._root)

    def _calculate_dynamic_columns(self) -> tuple[int, int]:
        available_width = self.scroll.viewport().width()
        available_width -= 20
        cell_width = _THUMB_BOX.width()
        min_width_per_cell = cell_width + _MIN_CELL_SPACING
        max_columns = max(1, (available_width + _MIN_CELL_SPACING) // min_width_per_cell)

        if max_columns == 1:
            spacing = _MIN_CELL_SPACING
        else:
            total_cell_width = max_columns * cell_width
            remaining_space = available_width - total_cell_width
            spacing_areas = max_columns + 1
            spacing = max(_MIN_CELL_SPACING, remaining_space // spacing_areas)
            spacing = min(spacing, _MAX_CELL_SPACING)

        return max_columns, spacing

    def populate(self, rel: str, folders: List[str], comics: List[str], root: Path) -> None:
        self._root = root
        self._rel = rel
        self._folders = folders.copy()
        self._comics = comics.copy()

        self.path_label.setText("/" + rel if rel else "/")
        self.change_btn.setVisible(rel == "")

        self._grid_items.clear()
        while self._grid.count():
            w = self._grid.takeAt(0).widget()
            if w:
                w.setParent(None)

        show = [(n, False) for n in self._folders] + [(n, True) for n in self._comics]

        if self._search_text:
            show = [(n, is_comic) for n, is_comic in show if self._search_text in n.lower()]
        if self._show_favorites_only and self._controller:
            lib = self._controller.library
            rel_prefix = self._rel + "/" if self._rel else ""
            show = [(n, is_comic) for n, is_comic in show if is_comic and lib.get_comic(rel_prefix + n).favorite]

        if self._grid_mode:
            columns, spacing = self._calculate_dynamic_columns()
            self._grid.setSpacing(spacing)
            self._grid.setContentsMargins(spacing, spacing, spacing, spacing)
        else:
            columns = 1

        for idx, (name, is_comic) in enumerate(show):
            if self._grid_mode:
                abs_path = root / rel / name
                preview = self._make_preview(abs_path, root) if is_comic else None
                handler = self._mk_click(name, is_comic)
                fav_toggle = self._mk_toggle_favorite(name) if is_comic else None
                comic_obj = self._controller.library.get_comic(
                    self._rel + "/" + name if self._rel else name) if self._controller and is_comic else None
                fav = comic_obj.favorite if comic_obj else False
                widget = _GridItem(name, preview, is_comic, self._icon_folder, self._icon_comic, handler, favorite=fav,
                                   toggle_fav_handler=fav_toggle)
                if is_comic:
                    self._grid_items[name] = widget
            else:
                widget = _ListItem(name, is_comic, self._icon_folder, self._icon_comic)
                widget.mouseReleaseEvent = self._mk_click(name, is_comic)

            row, col = divmod(idx, columns)
            self._grid.addWidget(widget, row, col)

        # ✅ Show/hide the empty label when needed
        self._empty_label.setVisible(len(show) == 0 and self._show_favorites_only)
        self.scroll.setVisible(len(show) > 0 or not self._show_favorites_only)

    def update_comic_favorite(self, comic_name: str, favorite: bool):
        if comic_name in self._grid_items:
            self._grid_items[comic_name].set_favorite(favorite)

    def _make_preview(self, path: Path, root: Path) -> Optional[QPixmap]:
        img = get_first_page_preview(path, root, _PREVIEW_MAX)
        return QPixmap.fromImage(img) if not img.isNull() else None

    def _mk_click(self, name: str, is_comic: bool):
        def _handler(event=None):
            if is_comic:
                self.comic_selected.emit(name)
            else:
                self.folder_selected.emit(name)
        return _handler

    def _mk_toggle_favorite(self, name: str):
        def _handler():
            self.favorite_toggled.emit(name)
        return _handler

    def _toggle_view(self) -> None:
        self._grid_mode = not self._grid_mode
        self.toggle_btn.setText("📄" if not self._grid_mode else "📂")
        if self._root is not None:
            self.populate(self._rel, self._folders, self._comics, self._root)

    def _toggle_favorites_view(self, on: bool) -> None:
        self._show_favorites_only = on
        if self._root is not None:
            self.populate(self._rel, self._folders, self._comics, self._root)

    def _live_filter(self, text: str) -> None:
        self._search_text = text.lower().strip()
        if self._root is not None:
            self.populate(self._rel, self._folders, self._comics, self._root)

    def _apply_search(self) -> None:
        self._search_text = self.search_box.text().lower().strip()
        if self._root is not None:
            self.populate(self._rel, self._folders, self._comics, self._root)
