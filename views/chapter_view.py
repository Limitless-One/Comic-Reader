from __future__ import annotations
from typing import List, TYPE_CHECKING

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QLabel, QListWidget, QListWidgetItem, QPushButton, QComboBox,
    QHBoxLayout, QVBoxLayout, QFrame, QStackedLayout
)

from models.comic_model import ComicState, ChapterState
from utils.images import get_comic_preview

if TYPE_CHECKING:
    from controllers.comic_controller import ComicController


class _ClickableLabel(QLabel):
    """A QLabel that emits a 'clicked' signal when pressed."""
    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class _ChapterRow(QWidget):
    """Custom widget for a single row in the chapter list."""
    bookmark_clicked = pyqtSignal(str)

    def __init__(self, chapter: ChapterState, is_dark: bool):
        super().__init__()
        self._key = chapter.path.name
        self.chapter = chapter
        self.is_dark = is_dark
        self.setToolTip(chapter.display_name)

        self.title_lbl = QLabel(chapter.display_name)

        self.star_btn = QPushButton("★")
        self.star_btn.setFlat(True)
        self.star_btn.setFixedSize(24, 24)
        self.star_btn.setCursor(Qt.PointingHandCursor)
        self.star_btn.clicked.connect(lambda: self.bookmark_clicked.emit(self._key))

        row = QHBoxLayout(self)
        row.setContentsMargins(15, 8, 15, 8)
        row.addWidget(self.title_lbl)
        row.addStretch()
        row.addWidget(self.star_btn)

        self.update_theme(is_dark)

    def _update_star_color(self, is_on: bool, is_dark: bool):
        color = "#ffdd57" if is_on else ("#777777" if is_dark else "#aaaaaa")
        self.star_btn.setStyleSheet(f"border:none; font-size:16px; color:{color};")

    def update_theme(self, is_dark: bool):
        """Updates widget colors without rebuilding it."""
        self.is_dark = is_dark
        if self.chapter.read:
            text_color = "#888888" if is_dark else "#aaaaaa"
        else:
            text_color = "#dcdcdc" if is_dark else "#111111"
        self.title_lbl.setStyleSheet(f"color: {text_color}; font-size: 14px;")
        self._update_star_color(self.chapter.bookmarked, is_dark)


class ChapterListView(QWidget):
    chapter_selected = pyqtSignal(str)
    bookmark_toggled = pyqtSignal(str)
    sort_changed = pyqtSignal(str, bool)
    reset_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    back_to_library = pyqtSignal()
    favorite_toggled = pyqtSignal()
    change_preview_requested = pyqtSignal()
    edit_metadata_requested = pyqtSignal()
    breadcrumb_clicked = pyqtSignal(list)

    def __init__(self, controller: "ComicController"):
        super().__init__()
        self.controller = controller
        self._is_dark = False
        self._current_path_parts: List[str] = []
        self._setup_ui()

    def _setup_ui(self):
        # --- Left Panel (Preview & Info) ---
        self.preview_container = QWidget()
        self.preview_container.setFixedSize(240, 340)

        self.preview_image = QLabel("Preview\nNot Available")
        self.preview_image.setAlignment(Qt.AlignCenter)
        self.preview_image.setObjectName("previewImage")

        self.edit_preview_btn = QPushButton("✎")
        self.edit_preview_btn.setFixedSize(32, 32)
        self.edit_preview_btn.setToolTip("Change Preview Image")
        self.edit_preview_btn.setObjectName("editPreviewBtn")
        self.edit_preview_btn.clicked.connect(self.change_preview_requested.emit)

        preview_stack = QStackedLayout(self.preview_container)
        preview_stack.addWidget(self.preview_image)
        preview_stack.addWidget(self.edit_preview_btn)
        preview_stack.setAlignment(self.edit_preview_btn, Qt.AlignBottom | Qt.AlignRight)
        preview_stack.setContentsMargins(5, 5, 5, 5)

        self.comic_label = QLabel("Comic Title")
        self.comic_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.comic_label.setWordWrap(True)
        self.comic_label.setAlignment(Qt.AlignCenter)

        self.edit_metadata_btn = QPushButton("Edit Metadata")
        self.edit_metadata_btn.clicked.connect(self.edit_metadata_requested.emit)

        self.tags_label = QLabel()
        self.tags_label.setWordWrap(True)
        self.tags_label.setAlignment(Qt.AlignTop)

        left_panel = QVBoxLayout()
        left_panel.setSpacing(15)
        left_panel.addWidget(self.preview_container, 0, Qt.AlignCenter)
        left_panel.addWidget(self.comic_label)
        left_panel.addWidget(self.edit_metadata_btn)
        left_panel.addWidget(self.tags_label, 1)

        # --- Right Panel (Chapter List & Controls) ---
        self.sort_dropdown = QComboBox()
        self.sort_dropdown.addItems(["Name ↑", "Name ↓", "Date Modified ↑", "Date Modified ↓"])
        self.sort_dropdown.currentIndexChanged.connect(self._on_sort_change)

        self.resume_btn = QPushButton("▶ Resume")
        self.resume_btn.clicked.connect(self.resume_requested.emit)

        self.reset_btn = QPushButton("⟳ Reset Progress")
        self.reset_btn.clicked.connect(self.reset_requested.emit)

        self.favorite_btn = QPushButton("★ Favorite")
        self.favorite_btn.setCheckable(True)
        self.favorite_btn.clicked.connect(self._on_favorite_clicked)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("Sort:"))
        controls_layout.addWidget(self.sort_dropdown)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.resume_btn)
        controls_layout.addWidget(self.reset_btn)
        controls_layout.addWidget(self.favorite_btn)

        self.chapter_list_widget = QListWidget()
        self.chapter_list_widget.itemClicked.connect(self._on_item_clicked)
        self.chapter_list_widget.setSpacing(5)

        right_panel = QVBoxLayout()
        right_panel.addLayout(controls_layout)
        right_panel.addWidget(self.chapter_list_widget)

        # --- Top Bar (Back & Breadcrumbs) ---
        self.back_btn = QPushButton("Back")
        self.back_btn.clicked.connect(self.back_to_library.emit)

        self.breadcrumb_widget = QWidget()
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_widget)
        self.breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        self.breadcrumb_layout.setSpacing(5)
        self.breadcrumb_layout.setAlignment(Qt.AlignLeft)

        top_bar_layout = QHBoxLayout()
        top_bar_layout.addWidget(self.back_btn)
        top_bar_layout.addWidget(self.breadcrumb_widget, 1)

        # --- Main Layout Assembly ---
        main_content_layout = QHBoxLayout()
        main_content_layout.setSpacing(20)
        main_content_layout.addLayout(left_panel, 1)
        main_content_layout.addLayout(right_panel, 2)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        main_layout.addLayout(top_bar_layout)
        main_layout.addLayout(main_content_layout)

        self.set_dark_mode(False)

    def load_chapters(self, comic: ComicState, chapters: List[ChapterState], path_parts: List[str]):
        self.comic_label.setText(comic.display_name)
        self.update_favorite_state(comic.favorite)
        self._current_path_parts = path_parts
        self._update_breadcrumbs()

        tags_text = ", ".join(f"{k}: {v}" for k, v in comic.metadata.items())
        self.tags_label.setText(f"Tags: {tags_text}" if tags_text else "No tags set.")

        self.chapter_list_widget.clear()
        for ch in chapters:
            row_widget = _ChapterRow(ch, self._is_dark)
            row_widget.bookmark_clicked.connect(self.bookmark_toggled.emit)

            item = QListWidgetItem(self.chapter_list_widget)
            item.setData(Qt.UserRole, ch.path.name)
            item.setSizeHint(row_widget.sizeHint())
            self.chapter_list_widget.addItem(item)
            self.chapter_list_widget.setItemWidget(item, row_widget)

        self._update_preview(comic.path)

    def _update_breadcrumbs(self):
        # Clear old breadcrumbs
        while self.breadcrumb_layout.count():
            child = self.breadcrumb_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Define colors based on theme
        link_color = "#8ab4f8" if self._is_dark else "#0057e7"
        text_color = "#dcdcdc" if self._is_dark else "#111111"

        # Add "Library" home link
        home_label = _ClickableLabel("Library")
        home_label.setStyleSheet(f"color: {link_color}; font-weight: bold;")
        home_label.clicked.connect(lambda: self.breadcrumb_clicked.emit([]))
        self.breadcrumb_layout.addWidget(home_label)

        # Add path parts
        cumulative_path = []
        for part in self._current_path_parts:
            cumulative_path.append(part)
            # Create a copy of the list for the lambda to capture correctly
            path_for_signal = list(cumulative_path)

            separator = QLabel(">")
            separator.setStyleSheet(f"color: {text_color};")
            self.breadcrumb_layout.addWidget(separator)

            part_label = _ClickableLabel(part)
            part_label.setStyleSheet(f"color: {link_color};")
            part_label.clicked.connect(lambda path=path_for_signal: self.breadcrumb_clicked.emit(path))
            self.breadcrumb_layout.addWidget(part_label)

        self.breadcrumb_layout.addStretch()

    def _update_preview(self, comic_path: Path):
        pixmap = get_comic_preview(comic_path)
        if pixmap and not pixmap.isNull():
            scaled_pix = pixmap.scaled(
                self.preview_image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.preview_image.setPixmap(scaled_pix)
            self.preview_image.setText("")
        else:
            self.preview_image.clear()
            self.preview_image.setText("Preview\nNot Available")

    def _on_item_clicked(self, item: QListWidgetItem):
        self.chapter_selected.emit(item.data(Qt.UserRole))

    def _on_sort_change(self, idx: int):
        key_map = [("name", False), ("name", True), ("date", False), ("date", True)]
        key, rev = key_map[idx]
        self.sort_changed.emit(key, rev)

    def _on_favorite_clicked(self):
        is_checked = self.favorite_btn.isChecked()
        self._update_favorite_style(is_checked)
        self.favorite_toggled.emit()

    def _update_favorite_style(self, is_favorite: bool):
        color = "#ffdd57" if is_favorite else ("#dcdcdc" if self._is_dark else "#555555")
        self.favorite_btn.setStyleSheet(f"color: {color};")

    def update_favorite_state(self, is_favorite: bool):
        self.favorite_btn.setChecked(is_favorite)
        self._update_favorite_style(is_favorite)

    def set_dark_mode(self, is_dark: bool):
        self._is_dark = is_dark
        self.update_favorite_state(self.favorite_btn.isChecked())
        preview_bg, edit_btn_bg, edit_btn_fg, tags_color = (
            ("#2b2b2b", "rgba(0,0,0,150)", "white", "#999") if is_dark
            else ("#ccc", "rgba(255,255,255,150)", "black", "#777")
        )
        self.tags_label.setStyleSheet(f"color: {tags_color}; font-style: italic;")
        self.setStyleSheet(f"""
            #previewImage {{ background-color: {preview_bg}; border-radius: 8px; }}
            #editPreviewBtn {{
                background-color: {edit_btn_bg}; color: {edit_btn_fg};
                border: none; border-radius: 16px; font-weight: bold; font-size: 16px;
            }}
            #editPreviewBtn:hover {{ background-color: rgba(0,0,0,200); }}
        """)

        # Update existing UI elements without rebuilding them
        self._update_breadcrumbs()
        for i in range(self.chapter_list_widget.count()):
            item = self.chapter_list_widget.item(i)
            widget = self.chapter_list_widget.itemWidget(item)
            if isinstance(widget, _ChapterRow):
                widget.update_theme(is_dark)

