from __future__ import annotations
import pillow_avif
import io
import zipfile
import rarfile
import fitz  # PyMuPDF
import ebooklib
from ebooklib import epub
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from natsort import natsorted
from PyQt5.QtGui import QPixmap

from .config import SUPPORTED_IMAGE_EXTS

# --- Phase 1: Lazy Loading and Caching Abstraction ---

class PageRef(ABC):
    """An abstract base class representing a reference to a single comic page."""
    _aspect_ratio: Optional[float] = None

    @lru_cache(maxsize=32)
    def get_pixmap(self) -> Optional[QPixmap]:
        """
        Loads the page's image data into a QPixmap.
        This method is cached using LRU for performance.
        """
        image_bytes = self.get_image_bytes()
        if not image_bytes:
            return None
        pixmap = QPixmap()
        pixmap.loadFromData(image_bytes)
        if not pixmap.isNull():
            self._aspect_ratio = pixmap.width() / pixmap.height()
        return pixmap

    def get_aspect_ratio(self) -> float:
        """Returns the aspect ratio of the page image, loading it if necessary."""
        if self._aspect_ratio is None:
            # Trigger pixmap loading which calculates the aspect ratio
            self.get_pixmap()
        return self._aspect_ratio if self._aspect_ratio is not None else 1.0

    @abstractmethod
    def get_image_bytes(self) -> Optional[bytes]:
        """Abstract method to retrieve the raw image bytes for the page."""
        raise NotImplementedError

class FolderPageRef(PageRef):
    """A page reference for an image file in a standard folder."""
    def __init__(self, path: Path):
        self.path = path

    def get_image_bytes(self) -> Optional[bytes]:
        try:
            return self.path.read_bytes()
        except OSError:
            return None

class ZipPageRef(PageRef):
    """A page reference for an image within a .cbz (zip) archive."""
    def __init__(self, zip_path: Path, member_name: str):
        self.zip_path = zip_path
        self.member_name = member_name

    def get_image_bytes(self) -> Optional[bytes]:
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                return zf.read(self.member_name)
        except (zipfile.BadZipFile, KeyError, OSError):
            return None

class PdfPageRef(PageRef):
    """A page reference for a page within a .pdf document."""
    def __init__(self, pdf_path: Path, page_num: int):
        self.pdf_path = pdf_path
        self.page_num = page_num

    def get_image_bytes(self) -> Optional[bytes]:
        try:
            with fitz.open(self.pdf_path) as doc:
                page = doc.load_page(self.page_num)
                # Render at a higher DPI for better quality
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
                return pix.tobytes("png")
        except Exception:
            return None

class EpubPageRef(PageRef):
    """A page reference for an image within an .epub file."""
    def __init__(self, epub_path: Path, item_id: str):
        self.epub_path = epub_path
        self.item_id = item_id

    def get_image_bytes(self) -> Optional[bytes]:
        try:
            book = epub.read_epub(self.epub_path)
            item = book.get_item_with_id(self.item_id)
            return item.get_content() if item else None
        except Exception:
            return None


# --- Main Public Functions ---

def _get_image_filenames(file_list: List[str]) -> List[str]:
    """Filters and sorts a list of filenames for supported images."""
    return natsorted([
        f for f in file_list
        if not f.startswith(('__MACOSX/', '.')) and Path(f).suffix.lower() in SUPPORTED_IMAGE_EXTS
    ])

def get_page_refs(path: Path) -> List[PageRef]:
    """
    Universal function to get a list of PageRef objects for any supported source.
    This is the new entry point for the ReaderView, enabling lazy loading.
    """
    if not path.exists():
        return []

    if path.is_dir():
        image_files = natsorted([p for p in path.iterdir() if p.suffix.lower() in SUPPORTED_IMAGE_EXTS])
        return [FolderPageRef(p) for p in image_files]

    ext = path.suffix.lower()
    if ext == '.cbz':
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                image_files = _get_image_filenames(zf.namelist())
                return [ZipPageRef(path, member) for member in image_files]
        except (zipfile.BadZipFile, OSError):
            return []
    if ext == '.pdf':
        try:
            with fitz.open(path) as doc:
                return [PdfPageRef(path, i) for i in range(doc.page_count)]
        except Exception:
            return []
    if ext == '.epub':
        try:
            book = epub.read_epub(path)
            image_items = natsorted(
                [i for i in book.get_items_of_type(ebooklib.ITEM_IMAGE)],
                key=lambda item: item.get_name()
            )
            return [EpubPageRef(path, item.get_id()) for item in image_items]
        except Exception:
            return []

    return []

def get_first_image_bytes(path: Path) -> Optional[bytes]:
    """
    Efficiently gets the raw bytes of the very first image from any source
    for generating thumbnails.
    """
    # Use the lazy-loading mechanism to get the first page reference
    page_refs = get_page_refs(path)
    if not page_refs:
        return None

    # Retrieve the image bytes from the first reference
    return page_refs[0].get_image_bytes()
