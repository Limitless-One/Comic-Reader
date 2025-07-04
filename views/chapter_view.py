from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QLabel, QListWidget, QListWidgetItem, QPushButton, QComboBox,
    QHBoxLayout, QVBoxLayout, QSpacerItem, QSizePolicy, QStyle, QFrame, QStackedLayout
)

from models import ComicState, ChapterState
from utils import chapter_is_image_folder, get_preview_path, load_and_scale_qimage, get_first_page_preview


class _StarButton(QPushButton):
    def __init__(self, on: bool):
        super().__init__("★")
        self._on = on
        self.setFlat(True)
        self.setFixedWidth(24)
        self.setCursor(Qt.PointingHandCursor)
        self._paint()

    def toggle_star(self):
        self._on = not self._on
        self._paint()

    def is_on(self) -> bool:
        return self._on

    def _paint(self):
        colour = "#ffcc00" if self._on else "#555555"
        self.setStyleSheet(f"border:none; font-size:16px; color:{colour};")


class _ChapterRow(QWidget):
    star_clicked = pyqtSignal(str)

    def __init__(self, chap: ChapterState):
        super().__init__()
        self._key = chap.path.name

        style = self.style()
        is_real_chapter = chapter_is_image_folder(chap.path) or chap.path.suffix.lower() == ".pdf"
        icon: QIcon = (
            style.standardIcon(QStyle.SP_FileIcon)
            if is_real_chapter else
            style.standardIcon(QStyle.SP_DirIcon)
        )

        icon_lbl = QLabel()
        icon_lbl.setPixmap(icon.pixmap(24, 24))

        title_lbl = QLabel(chap.display_name)
        title_lbl.setStyleSheet(f"color:{'#aaaaaa' if chap.read else '#000000'};")
        title_lbl.setToolTip(chap.display_name)

        if is_real_chapter:
            star_btn = _StarButton(chap.bookmarked)
            star_btn.clicked.connect(lambda: self.star_clicked.emit(self._key))
            self._star_btn = star_btn
        else:
            star_btn = QLabel()
            self._star_btn = None

        row = QHBoxLayout()
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(12)
        row.addWidget(icon_lbl)
        row.addWidget(title_lbl)
        row.addItem(QSpacerItem(20, 20, QSizePolicy.Expanding))
        row.addWidget(star_btn)

        container = QFrame()
        container.setLayout(row)
        container.setStyleSheet("background-color: #ddd; border-radius: 8px;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 10)
        outer.addWidget(container)

    def set_bookmarked(self, on: bool):
        if self._star_btn and isinstance(self._star_btn, _StarButton):
            if on != self._star_btn.is_on():
                self._star_btn.toggle_star()


class ChapterListView(QWidget):
    chapter_selected = pyqtSignal(str)
    bookmark_toggled = pyqtSignal(str)
    sort_changed     = pyqtSignal(str, bool)
    reset_requested  = pyqtSignal()
    resume_requested = pyqtSignal()
    back_to_library  = pyqtSignal()
    favorite_toggled = pyqtSignal()
    change_preview_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.preview_image = QLabel()
        self.preview_image.setFixedSize(240, 300)

        self.edit_preview_btn = QPushButton("✎")
        self.edit_preview_btn.setFixedSize(32, 32)
        self.edit_preview_btn.setToolTip("Change Preview Image")
        self.edit_preview_btn.setStyleSheet(
            "padding: 2px; border: none; background-color: rgba(0, 0, 0, 200); "
            "color: white; font-weight: bold; border-radius: 4px;"
        )
        self.edit_preview_btn.clicked.connect(self.change_preview_requested.emit)

        self.preview_container = QWidget()
        self.preview_container.setFixedSize(240, 300)
        self.preview_container.setStyleSheet("background-color: transparent;")
        preview_stack = QStackedLayout(self.preview_container)
        preview_stack.addWidget(self.preview_image)
        preview_stack.setStackingMode(QStackedLayout.StackAll)

        self.preview_image.raise_()
        self.edit_preview_btn.setParent(self.preview_container)
        self.edit_preview_btn.move(204, 264)
        self.edit_preview_btn.raise_()

        self.comic_label = QLabel("Comic Title")
        self.comic_label.setStyleSheet("font-size: 20px; font-weight: bold; color: black;")

        self.sort_dropdown = QComboBox()
        self.sort_dropdown.setToolTip("Sort Chapters")
        self.sort_dropdown.addItems([
            "Name ↑", "Name ↓", "Date Modified ↑", "Date Modified ↓"
        ])
        self.sort_dropdown.currentIndexChanged.connect(self._handle_sort_change)

        self.resume_btn = QPushButton("▶")
        self.resume_btn.setToolTip("Resume Reading")
        self.resume_btn.clicked.connect(self.resume_requested.emit)

        self.reset_btn = QPushButton("⟳")
        self.reset_btn.setToolTip("Reset Progress")
        self.reset_btn.clicked.connect(self.reset_requested.emit)

        self.favorite_btn = QPushButton("★")
        self.favorite_btn.setToolTip("Toggle Favorite")
        self.favorite_btn.setStyleSheet("color: #555555; font-size: 18px; border: none;")
        self.favorite_btn.setCheckable(True)
        self.favorite_btn.clicked.connect(self._on_favorite_clicked)

        self.list = QListWidget()
        self.list.itemClicked.connect(self._emit_selected)

        self.back_btn = QPushButton("← Back")
        self.back_btn.setToolTip("Back to Previous Page")
        self.back_btn.clicked.connect(self.back_to_library.emit)

        top_row = QHBoxLayout()
        top_row.addWidget(self.back_btn)
        top_row.addStretch(1)

        header_layout = QVBoxLayout()
        header_layout.addLayout(top_row)
        header_layout.addWidget(self.preview_container, alignment=Qt.AlignCenter)

        control_row = QHBoxLayout()
        control_row.addStretch(1)
        control_row.addWidget(QLabel("Sort by:"))
        control_row.addWidget(self.sort_dropdown)
        control_row.addWidget(self.resume_btn)
        control_row.addWidget(self.reset_btn)
        control_row.addWidget(self.favorite_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(header_layout)
        layout.addWidget(self.comic_label, alignment=Qt.AlignCenter)
        layout.addLayout(control_row)

        self.divider = QFrame()
        self.divider.setFrameShape(QFrame.HLine)
        self.divider.setFrameShadow(QFrame.Sunken)
        self.divider.setStyleSheet("background-color: #888888; height: 1px;")
        layout.addWidget(self.divider)

        layout.addWidget(self.list)

        self._sort_key = "name"
        self._sort_rev = False

    def load_chapters(self, comic: ComicState, chapters: List[ChapterState], comic_root: Path):
        self.comic_label.setText(comic.display_name)
        self.favorite_btn.setChecked(getattr(comic, "favorite", False))
        self._update_fav_btn_color(self.favorite_btn.isChecked())

        self.list.clear()
        for ch in chapters:
            row_widget = _ChapterRow(ch)
            row_widget.star_clicked.connect(self.bookmark_toggled.emit)
            item = QListWidgetItem(self.list)
            item.setData(Qt.UserRole, ch.path.name)
            item.setSizeHint(row_widget.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row_widget)

        preview_path = get_preview_path(comic.path, comic_root)
        if not preview_path.exists():
            image = get_first_page_preview(comic.path, comic_root, (240, 300))
            if not image.isNull():
                preview_path.parent.mkdir(parents=True, exist_ok=True)
                image.save(str(preview_path), "JPEG")

        if preview_path.exists():
            pix = QPixmap.fromImage(load_and_scale_qimage(preview_path, (240, 300)))
            self.preview_image.setPixmap(pix)
        else:
            self.preview_image.clear()

    def _emit_selected(self, item: QListWidgetItem):
        self.chapter_selected.emit(item.data(Qt.UserRole))

    def _handle_sort_change(self, idx: int):
        key_map = [
            ("name", False), ("name", True),
            ("date", False), ("date", True)
        ]
        key, rev = key_map[idx]
        self._sort_key, self._sort_rev = key, rev
        self.sort_changed.emit(key, rev)

    def _update_fav_btn_color(self, on: bool):
        color = "#ffcc00" if on else "#555555"
        self.favorite_btn.setStyleSheet(f"color: {color}; font-size: 18px; border: none;")

    def _on_favorite_clicked(self):
        self._update_fav_btn_color(self.favorite_btn.isChecked())
        self.favorite_toggled.emit()

    def update_favorite_state(self, favorite: bool):
        """Update the favorite button state without triggering the signal"""
        self.favorite_btn.setChecked(favorite)
        self._update_fav_btn_color(favorite)