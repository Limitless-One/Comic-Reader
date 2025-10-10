from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Optional

from PyQt5.QtCore import Qt, QSize, pyqtSignal, QEvent, QTimer, pyqtSlot, QByteArray
from PyQt5.QtGui import QPixmap, QFontMetrics, QCursor, QMovie, QIcon, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QToolButton, QHBoxLayout, QVBoxLayout,
    QGridLayout, QScrollArea, QStyle, QLineEdit, QFrame, QCheckBox
)
from natsort import natsort_key

from utils.ui import calculate_dynamic_grid_columns
from utils.config import THUMB_BOX_SIZE, PREVIEW_MAX_SIZE
from utils.images import PreviewWorker

# SVG icons for settings (cog) and theme toggle (sun/moon)
GEAR_ICON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
  <circle cx="12" cy="12" r="3"/>
</svg>
"""

SUN_ICON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="5"/>
  <line x1="12" y1="1" x2="12" y2="3"/>
  <line x1="12" y1="21" x2="12" y2="23"/>
  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
  <line x1="1" y1="12" x2="3" y2="12"/>
  <line x1="21" y1="12" x2="23" y2="12"/>
  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
</svg>
"""

MOON_ICON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
</svg>
"""


def get_svg_icon(svg_data: str, color="currentColor") -> QIcon:
    """Creates a QIcon from SVG data, allowing color override."""
    try:
        full_svg = svg_data.replace('stroke="currentColor"', f'stroke="{color}"')
        full_svg = full_svg.replace('fill="currentColor"', f'fill="{color}"')

        renderer = QSvgRenderer(QByteArray(full_svg.encode('utf-8')))
        pixmap = QPixmap(renderer.defaultSize())
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        return QIcon(pixmap)
    except:
        # Return empty icon if SVG rendering fails
        return QIcon()


class _GridItem(QWidget):
    def __init__(self, name: str, is_comic: bool, click_handler, fav_handler, is_fav: bool):
        super().__init__()
        self.setFixedSize(QSize(*THUMB_BOX_SIZE))
        self.setCursor(Qt.PointingHandCursor)
        self._name = name

        self.container = QFrame(self)
        self.container.setObjectName("gridItem")
        self.container.setGeometry(0, 0, *THUMB_BOX_SIZE)
        lay = QVBoxLayout(self.container)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self.preview_lbl = QLabel()
        self.preview_lbl.setFixedSize(*PREVIEW_MAX_SIZE)
        self.preview_lbl.setAlignment(Qt.AlignCenter)
        self.preview_lbl.setObjectName("previewLabel")
        fallback_icon = (
            self.style().standardIcon(QStyle.SP_FileIcon) if is_comic
            else self.style().standardIcon(QStyle.SP_DirIcon)
        )
        self.preview_lbl.setPixmap(fallback_icon.pixmap(64, 64))

        self.loading_movie = QMovie(":/qt-project.org/styles/commonstyle/images/spinner-32-alpha.gif")
        self.loading_movie.setScaledSize(QSize(32, 32))
        self.loading_indicator = QLabel(self.preview_lbl)
        self.loading_indicator.setMovie(self.loading_movie)
        self.loading_indicator.setAlignment(Qt.AlignCenter)
        self.loading_indicator.setGeometry(0, 0, *PREVIEW_MAX_SIZE)
        self.loading_indicator.hide()

        self.fav_btn = None
        if is_comic:
            self.fav_btn = QToolButton(self.preview_lbl)
            self.fav_btn.setText("★")
            self.fav_btn.setCheckable(True)
            self.fav_btn.setChecked(is_fav)
            self.fav_btn.setFixedSize(24, 24)
            self.fav_btn.move(self.preview_lbl.width() - 28, 4)
            self.fav_btn.clicked.connect(lambda: fav_handler())
            self.update_fav_color()

        fm = QFontMetrics(self.font())
        elided_name = fm.elidedText(name, Qt.ElideRight, PREVIEW_MAX_SIZE[0] - 10)
        self.title_lbl = QLabel(elided_name)
        self.title_lbl.setToolTip(name)
        self.title_lbl.setAlignment(Qt.AlignCenter)

        lay.addWidget(self.preview_lbl, 1, Qt.AlignCenter)
        lay.addWidget(self.title_lbl, 0, Qt.AlignCenter)

        self.mousePressEvent = lambda e: click_handler()

    def set_loading(self, is_loading: bool):
        if is_loading:
            self.loading_indicator.show()
            self.loading_movie.start()
        else:
            self.loading_movie.stop()
            self.loading_indicator.hide()

    def set_preview(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            self.preview_lbl.setPixmap(
                pixmap.scaled(self.preview_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def set_favorite(self, is_fav: bool):
        if self.fav_btn:
            self.fav_btn.setChecked(is_fav)
            self.update_fav_color()

    def update_fav_color(self, is_dark: bool = False):
        if not self.fav_btn: return
        fav_color = "#ffdd57" if self.fav_btn.isChecked() else "#888"
        self.fav_btn.setStyleSheet(f"""
            QToolButton {{
                background-color: rgba(0, 0, 0, 100); border-radius: 12px;
                font-size: 14px; color: {fav_color};
            }}
            QToolButton:hover {{ color: #ffdd57; }}
        """)


class _ListItem(QWidget):
    """Custom widget for list view mode."""

    def __init__(self, name: str, is_comic: bool, click_handler, fav_handler, is_fav: bool):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)

        self.container = QFrame()
        self.container.setObjectName("listItem")
        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(10, 5, 10, 5)

        self.fav_btn = None
        if is_comic:
            self.fav_btn = QToolButton(text="★")
            self.fav_btn.setCheckable(True)
            self.fav_btn.setChecked(is_fav)
            self.fav_btn.setFixedSize(24, 24)
            self.fav_btn.clicked.connect(fav_handler)
            self.update_fav_color()
            layout.addWidget(self.fav_btn)

        icon = self.style().standardIcon(QStyle.SP_FileIcon if is_comic else QStyle.SP_DirIcon)
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(24, 24))

        title_label = QLabel(name)
        title_label.mousePressEvent = lambda e: click_handler()

        layout.addWidget(icon_label)
        layout.addWidget(title_label, 1)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 2)
        main_layout.addWidget(self.container)

    def set_favorite(self, is_fav: bool):
        if self.fav_btn:
            self.fav_btn.setChecked(is_fav)
            self.update_fav_color()

    def update_fav_color(self):
        if not self.fav_btn: return
        color = "#ffdd57" if self.fav_btn.isChecked() else "#aaaaaa"
        self.fav_btn.setStyleSheet(f"background: transparent; border: none; font-size: 16px; color: {color};")


class LibraryView(QWidget):
    item_selected = pyqtSignal(Path, bool)
    back_requested = pyqtSignal()
    manage_library_requested = pyqtSignal()
    favorite_toggled = pyqtSignal(str)
    search_updated = pyqtSignal(str, bool)
    settings_requested = pyqtSignal()
    theme_toggled = pyqtSignal(bool)

    def __init__(self, controller):
        super().__init__()
        self._controller = controller
        self._is_dark = False
        self._grid_mode = True
        self.roots: List[Path] = []
        self.all_items: Dict[str, Dict] = {}
        self.grid_item_widgets: Dict[str, QWidget] = {}

        self._setup_ui()
        self._render_debounce_timer = QTimer(self)
        self._render_debounce_timer.setSingleShot(True)
        self._render_debounce_timer.setInterval(100)
        self._render_debounce_timer.timeout.connect(self._render_items)

    def _setup_ui(self):
        self.up_btn = QPushButton("↑ Up")
        self.up_btn.clicked.connect(self.back_requested.emit)

        self.path_label = QLabel("/")
        self.path_label.setObjectName("pathLabel")

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search...")
        self.search_box.textChanged.connect(self._on_search_text_changed)

        self.deep_search_checkbox = QCheckBox("Deep Search")
        self.deep_search_checkbox.setToolTip("Search all subfolders")
        self.deep_search_checkbox.stateChanged.connect(self._on_search_text_changed)

        self.manage_btn = QPushButton("Manage Library")
        self.manage_btn.clicked.connect(self.manage_library_requested.emit)

        self.view_toggle_btn = QToolButton()
        self.view_toggle_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        self.view_toggle_btn.setToolTip("Toggle List/Grid View")
        self.view_toggle_btn.clicked.connect(self._toggle_view_mode)

        self.fav_btn = QToolButton(text="★")
        self.fav_btn.setToolTip("Show only favorites")
        self.fav_btn.setCheckable(True)
        self.fav_btn.toggled.connect(self._trigger_render)

        self.settings_btn = QToolButton()
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self.settings_requested.emit)

        self.theme_btn = QToolButton()
        self.theme_btn.setToolTip("Toggle Light/Dark Mode")
        self.theme_btn.setCheckable(True)
        self.theme_btn.toggled.connect(self.theme_toggled.emit)

        bar = QHBoxLayout()
        bar.addWidget(self.up_btn)
        bar.addWidget(self.path_label, 1)
        bar.addStretch(1)
        bar.addWidget(self.search_box, 2)
        bar.addWidget(self.deep_search_checkbox)
        bar.addStretch(1)
        bar.addWidget(self.manage_btn)
        bar.addWidget(self.view_toggle_btn)
        bar.addWidget(self.fav_btn)
        bar.addWidget(self.theme_btn)
        bar.addWidget(self.settings_btn)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        self.scroll_area.setWidget(self.content_widget)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(bar)
        main_layout.addWidget(self.scroll_area)
        self.set_dark_mode(False)

    def populate(self, rel_path: str, folders: List[Path], comics: List[Path], roots: List[Path]):
        self.roots = roots
        self.path_label.setText(f"/{rel_path}" if rel_path else "Library Home")
        self.up_btn.setEnabled(bool(rel_path) or len(self.roots) > 1 or self.is_deep_search_active())

        self.all_items.clear()
        for path in folders:
            self.all_items[path.as_posix()] = {'path': path, 'is_comic': False}
        for path in comics:
            key = self._controller.library._get_comic_key_from_path(path)
            if not key: continue
            comic_state = self._controller.library.get_comic(key)
            is_fav = comic_state.favorite if comic_state else False
            self.all_items[key] = {'path': path, 'is_comic': True, 'favorite': is_fav}

        self._trigger_render()

    def _trigger_render(self):
        self._render_debounce_timer.start()

    def _render_items(self):
        self.content_widget.hide()

        if self.scroll_area.widget():
            self.scroll_area.widget().deleteLater()
        self.grid_item_widgets.clear()

        self.content_widget = QWidget()
        layout = QGridLayout(self.content_widget) if self._grid_mode else QVBoxLayout(self.content_widget)
        layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.content_widget)

        items_to_show = list(self.all_items.values())
        if self.fav_btn.isChecked():
            items_to_show = [i for i in items_to_show if i.get('favorite', False)]

        items_to_show.sort(key=lambda x: natsort_key(x['path'].name))

        if not items_to_show:
            msg = "No results found." if self.is_deep_search_active() else "This folder is empty."
            no_items_label = QLabel(msg)
            no_items_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(no_items_label)
        else:
            if self._grid_mode:
                cols, spacing = calculate_dynamic_grid_columns(self.width())
                layout.setSpacing(spacing)
                for i, item_data in enumerate(items_to_show):
                    self._add_item_widget(item_data, i // cols, i % cols, layout)
            else:
                layout.setSpacing(0)
                for i, item_data in enumerate(items_to_show):
                    self._add_item_widget(item_data, i, 0, layout)
                layout.addStretch(1)

        self.content_widget.show()

    def _add_item_widget(self, item_data: Dict, row: int, col: int, layout: QGridLayout | QVBoxLayout):
        path = item_data['path']
        is_comic = item_data['is_comic']
        key = self._controller.library._get_comic_key_from_path(path) if is_comic else path.as_posix()
        if not key: return

        click_handler = lambda p=path, c=is_comic: self.item_selected.emit(p, c)
        fav_handler = lambda k=key: self.favorite_toggled.emit(k)

        if self._grid_mode:
            widget = _GridItem(path.name, is_comic, click_handler, fav_handler, item_data.get('favorite', False))
            widget.update_fav_color(self._is_dark)
            if is_comic:
                widget.set_loading(True)
                worker = PreviewWorker(path, self._controller.library)
                worker.signals.finished.connect(self.on_preview_loaded)
                self._controller.threadpool.start(worker)
            layout.addWidget(widget, row, col)
        else:
            widget = _ListItem(path.name, is_comic, click_handler, fav_handler, item_data.get('favorite', False))
            layout.addWidget(widget)

        self.grid_item_widgets[key] = widget

    @pyqtSlot(str, QPixmap)
    def on_preview_loaded(self, key: str, pixmap: QPixmap):
        if key in self.grid_item_widgets:
            item = self.grid_item_widgets[key]
            if isinstance(item, _GridItem):
                item.set_loading(False)
                item.set_preview(pixmap)

    def update_comic_favorite_state(self, comic_key: str, is_fav: bool):
        if comic_key in self.all_items:
            self.all_items[comic_key]['favorite'] = is_fav
        if comic_key in self.grid_item_widgets:
            item = self.grid_item_widgets[comic_key]
            if isinstance(item, (_GridItem, _ListItem)):
                item.set_favorite(is_fav)

        if self.fav_btn.isChecked():
            self._trigger_render()

    def refresh_item_preview(self, comic_key: str):
        if comic_key in self.grid_item_widgets:
            item_widget = self.grid_item_widgets[comic_key]
            item_data = self.all_items.get(comic_key)
            if not item_data or not isinstance(item_widget, _GridItem): return

            item_widget.set_loading(True)
            worker = PreviewWorker(item_data['path'], self._controller.library, force_refresh=True)
            worker.signals.finished.connect(self.on_preview_loaded)
            self._controller.threadpool.start(worker)

    def _toggle_view_mode(self):
        self._grid_mode = not self._grid_mode
        icon = self.style().standardIcon(
            QStyle.SP_FileDialogDetailedView if self._grid_mode else QStyle.SP_FileDialogListView
        )
        self.view_toggle_btn.setIcon(icon)
        self._trigger_render()

    def _on_search_text_changed(self):
        self.search_updated.emit(self.search_box.text(), self.deep_search_checkbox.isChecked())

    def is_deep_search_active(self) -> bool:
        return bool(self.deep_search_checkbox.isChecked() and self.search_box.text())

    def clear_search(self):
        self.search_box.clear()
        self.deep_search_checkbox.setChecked(False)
        self._on_search_text_changed()

    def set_dark_mode(self, is_dark: bool):
        self._is_dark = is_dark
        base_bg, item_bg, item_border, text_color, preview_bg, path_color, list_hover = (
            ("#3c3c3c", "#2a2a2a", "#444", "#dcdcdc", "#333", "#999", "#4f4f4f") if is_dark else
            ("#f0f0f0", "#ffffff", "#cccccc", "#111111", "#e0e0e0", "#777", "#e9e9e9")
        )
        icon_color = "#dcdcdc" if is_dark else "#333333"

        self.setStyleSheet(f"""
            LibraryView, QScrollArea {{ background-color: {base_bg}; }}
            #pathLabel {{ color: {path_color}; font-style: italic; }}
            #gridItem {{ background-color: {item_bg}; border: 1px solid {item_border}; border-radius: 8px; }}
            #gridItem QLabel {{ color: {text_color}; }}
            #previewLabel {{ background-color: {preview_bg}; border-radius: 4px; }}
            #listItem {{ background-color: transparent; border-radius: 4px; border: 1px solid {item_border}; }}
            #listItem QLabel {{ color: {text_color}; }}
            #listItem:hover {{ background-color: {list_hover}; }}
        """)

        # Set custom SVG icons with theme-aware colors
        self.settings_btn.setIcon(get_svg_icon(GEAR_ICON_SVG, icon_color))
        self.theme_btn.setIcon(get_svg_icon(MOON_ICON_SVG if is_dark else SUN_ICON_SVG, icon_color))

        for item in self.grid_item_widgets.values():
            if hasattr(item, 'update_fav_color'):
                item.update_fav_color(is_dark)

        self.theme_btn.setChecked(is_dark)

    def resizeEvent(self, event: QEvent):
        super().resizeEvent(event)
        self.content_widget.hide()
        self._trigger_render()
