from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import QObject, pyqtSignal, QRunnable, pyqtSlot

from .archive_handler import get_first_image_bytes
from .paths import get_preview_cache_path

# Phase 1: Background Worker for Preview Generation

class WorkerSignals(QObject):
    """Defines signals available from a running worker thread."""
    finished = pyqtSignal(str, QPixmap)  # comic_key, preview_pixmap

class PreviewWorker(QRunnable):
    """Worker thread for generating a single comic preview."""
    def __init__(self, comic_path: Path, library, force_refresh: bool = False):
        super().__init__()
        self.comic_path = comic_path
        self.library = library
        self.force_refresh = force_refresh
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        """Execute the preview generation task."""
        key = self.library._get_comic_key_from_path(self.comic_path)
        if not key:
            return

        pixmap = get_comic_preview(self.comic_path, self.force_refresh)
        if pixmap:
            self.signals.finished.emit(key, pixmap)


def get_comic_preview(comic_path: Path, force_refresh: bool = False) -> Optional[QPixmap]:
    """
    Generates and caches a preview for a comic. This is the core logic
    called by the background worker.
    """
    preview_path = get_preview_cache_path(comic_path)

    # 1. Use cached preview if it exists and we're not forcing a refresh
    if not force_refresh and preview_path.exists():
        pixmap = QPixmap(str(preview_path))
        if not pixmap.isNull():
            return pixmap

    # 2. Determine the source for the preview image
    # For a folder-comic, use its first chapter/item as the source
    source_path = comic_path
    if comic_path.is_dir():
        try:
            children = sorted(
                [p for p in comic_path.iterdir() if not p.name.startswith('.')],
                key=lambda p: p.name
            )
            if children:
                source_path = children[0]
        except OSError:
            return None

    # 3. Get raw bytes of the first image
    image_bytes = get_first_image_bytes(source_path)
    if not image_bytes:
        return None

    # 4. Create QImage, save to cache, and return as QPixmap
    try:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        img = QImage()
        if not img.loadFromData(image_bytes):
            return None
        # Save with good quality; UI will handle scaling
        img.save(str(preview_path), "JPEG", 85)
        return QPixmap(str(preview_path))
    except OSError as e:
        print(f"[ERROR] Could not save preview for {comic_path.name}: {e}")
        return None

def save_custom_preview(comic_path: Path, new_image_path: Path):
    """Overwrites the cached preview with a user-selected image."""
    if not new_image_path.is_file():
        return

    preview_path = get_preview_cache_path(comic_path)
    preview_path.parent.mkdir(parents=True, exist_ok=True)

    custom_img = QImage(str(new_image_path))
    if not custom_img.isNull():
        custom_img.save(str(preview_path), "JPEG", 90)
