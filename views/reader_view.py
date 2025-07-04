from __future__ import annotations
from pathlib import Path
from typing import List

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QComboBox,
    QToolButton,
)

from models import ChapterState
from utils import chapter_is_image_folder

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


class ReaderView(QWidget):
    """Scrollable comic reader with page/chapter navigation."""

    back_to_chapters = pyqtSignal()
    chapter_requested = pyqtSignal(str)  # emits chapter_key

    _MAX_W = 900
    _SCROLL_STEP = 120  # pixels for ↑/↓

    # ────────────── INIT ───────────────────────────────────────────────
    def __init__(self) -> None:
        super().__init__()

        #  Toolbar ------------------------------------------------------
        self.back_btn = QPushButton("← Chapters")
        self.back_btn.clicked.connect(self.back_to_chapters.emit)

        self.chapter_box = QComboBox()
        self.chapter_box.currentIndexChanged.connect(self._dropdown_change)

        self.prev_btn = QToolButton(text="◀")
        self.next_btn = QToolButton(text="▶")
        self.prev_btn.clicked.connect(lambda: self._navigate(-1))
        self.next_btn.clicked.connect(lambda: self._navigate(+1))

        self.mode_btn = QPushButton("Single Page")
        self.mode_btn.setCheckable(True)
        self.mode_btn.toggled.connect(self._toggle_mode)

        self.dark_btn = QPushButton("☾")
        self.dark_btn.setCheckable(True)
        self.dark_btn.toggled.connect(
            lambda on: self.setStyleSheet(
                "background:#121212;color:#ddd;" if on else ""
            )
        )

        # Remove focus so arrow keys reach view
        for w in (
            self.prev_btn,
            self.next_btn,
            self.mode_btn,
            self.dark_btn,
            self.chapter_box,
        ):
            w.setFocusPolicy(Qt.NoFocus)

        bar = QHBoxLayout()
        bar.addWidget(self.back_btn)
        bar.addWidget(self.chapter_box, stretch=1)
        bar.addWidget(self.prev_btn)
        bar.addWidget(self.next_btn)
        bar.addWidget(self.mode_btn)
        bar.addWidget(self.dark_btn)

        #  Scroll area --------------------------------------------------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.container)

        root = QVBoxLayout(self)
        root.addLayout(bar)
        root.addWidget(self.scroll)

        # receive key events
        self.setFocusPolicy(Qt.StrongFocus)

        # state vars
        self._pages: List[QPixmap] = []
        self._single_page = False
        self._page_idx = 0
        self._chapter_keys: List[str] = []
        self._current_key: str | None = None

    # ────────────── PUBLIC API ─────────────────────────────────────────
    def load_chapter(
        self, chapter: ChapterState, chapter_order: List[ChapterState]
    ) -> None:
        """Controller calls this every time a chapter is opened."""
        self._chapter_keys = [c.path.name for c in chapter_order]
        self._current_key = chapter.path.name

        # Populate dropdown
        self.chapter_box.blockSignals(True)
        self.chapter_box.clear()
        for ch in chapter_order:
            self.chapter_box.addItem(ch.display_name, ch.path.name)
        idx = self.chapter_box.findData(self._current_key)
        self.chapter_box.setCurrentIndex(max(0, idx))
        self.chapter_box.blockSignals(False)

        # Load pages
        self._pages = self._extract_pages(chapter.path)
        self._page_idx = 0
        self._render()

        #self.setFocus(Qt.OtherFocusReason)   # ensure arrow keys work

    # ────────────── DROPDOWN ───────────────────────────────────────────
    def _dropdown_change(self, i: int):
        key = self.chapter_box.itemData(i)
        if key and key != self._current_key:
            self.chapter_requested.emit(key)

    # ────────────── NAVIGATION ─────────────────────────────────────────
    def _navigate(self, delta: int):
        if self._single_page:
            self._page_idx = (self._page_idx + delta) % len(self._pages)
            self._render()
        else:
            if self._current_key in self._chapter_keys:
                i = (self._chapter_keys.index(self._current_key) + delta) % len(
                    self._chapter_keys
                )
                self.chapter_requested.emit(self._chapter_keys[i])

    # ────────────── PAGE MODE ──────────────────────────────────────────
    def _toggle_mode(self, on: bool):
        self._single_page = on
        self.mode_btn.setText("Single Page" if on else "All Pages")
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)
        self._render()

    # ────────────── KEY EVENTS ─────────────────────────────────────────
    def keyPressEvent(self, e):  # type: ignore
        if e.key() == Qt.Key_Left:
            self._navigate(-1)
        elif e.key() == Qt.Key_Right:
            self._navigate(+1)
        elif e.key() == Qt.Key_Down:
            bar = self.scroll.verticalScrollBar()
            bar.setValue(bar.value() + self._SCROLL_STEP)
        elif e.key() == Qt.Key_Up:
            bar = self.scroll.verticalScrollBar()
            bar.setValue(bar.value() - self._SCROLL_STEP)
        else:
            super().keyPressEvent(e)

    # ────────────── RENDERING ──────────────────────────────────────────
    def _render(self):
        while self.vbox.count():
            w = self.vbox.takeAt(0).widget()
            if w:
                w.setParent(None)

        if self._single_page and self._pages:
            self._add_pix(self._pages[self._page_idx])
        else:
            for p in self._pages:
                self._add_pix(p)

        self.scroll.verticalScrollBar().setValue(0)

    def _add_pix(self, pix: QPixmap):
        if pix.width() > self._MAX_W:
            pix = pix.scaledToWidth(self._MAX_W, Qt.SmoothTransformation)
        lbl = QLabel(alignment=Qt.AlignCenter)
        lbl.setPixmap(pix)
        self.vbox.addWidget(lbl)

    # ────────────── LOAD PAGES ─────────────────────────────────────────
    def _extract_pages(self, path: Path) -> List[QPixmap]:
        out: List[QPixmap] = []
        if path.is_dir():
            imgs = sorted(
                (p for p in path.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"})
            )
            for img in imgs:
                out.append(self._load_image(img))
        elif path.suffix.lower() == ".pdf" and fitz:
            doc = fitz.open(str(path))
            for page in doc:
                pix = page.get_pixmap(dpi=150)
                img = QImage(
                    pix.samples,
                    pix.width,
                    pix.height,
                    pix.stride,
                    QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888,
                )
                out.append(QPixmap.fromImage(img))
            doc.close()
        return out

    def _load_image(self, img: Path) -> QPixmap:
        pix = QPixmap(str(img))
        if pix.width() > self._MAX_W:
            pix = pix.scaledToWidth(self._MAX_W, Qt.SmoothTransformation)
        return pix
