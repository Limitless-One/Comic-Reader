from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from shutil import copyfile
from PIL import Image

# Optional PDF preview (requires PyMuPDF)
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore

SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
PREVIEW_DIR_NAME = ".comic_previews"
DEFAULT_THUMB_SIZE = (160, 225)

# ────────────────────────────────────────────────────────────────
# Generic helpers
# ────────────────────────────────────────────────────────────────

def chapter_is_image_folder(path: Path) -> bool:
    """True if folder contains only images (treat as a 'chapter')."""
    if not path.is_dir():
        return False
    imgs = [p for p in path.iterdir() if p.suffix.lower() in SUPPORTED_IMAGE_EXTS]
    others = [p for p in path.iterdir() if p not in imgs]
    return bool(imgs) and not others

def load_and_scale_qimage(path: Path, max_size: Tuple[int, int] = DEFAULT_THUMB_SIZE) -> QImage:
    """Load an image file and scale it proportionally to fit *max_size*."""
    img = QImage(str(path))
    return img.scaled(*max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

def get_first_page_preview(comic_path: Path, comic_root: Path, thumb_size: Tuple[int, int] = DEFAULT_THUMB_SIZE) -> QImage:
    """Return a QImage for the comic's preview. Generate and store default if missing."""
    preview_path = get_preview_path(comic_path, comic_root)
    if preview_path.exists():
        return load_and_scale_qimage(preview_path, thumb_size)

    # Handle directories with chapters inside
    if comic_path.is_dir():
        candidates = sorted([p for p in comic_path.iterdir() if not p.name.startswith(".")])
        for chapter_path in candidates:
            if chapter_is_image_folder(chapter_path):
                first_img = sorted(chapter_path.iterdir())[0]
                img = load_and_scale_qimage(first_img, thumb_size)
                img.save(str(preview_path))
                return img
            elif chapter_path.suffix.lower() == ".pdf" and fitz:
                try:
                    doc = fitz.open(str(chapter_path))
                    page = doc.load_page(0)
                    pix = page.get_pixmap(dpi=96)
                    img = QImage(
                        pix.samples,
                        pix.width,
                        pix.height,
                        pix.stride,
                        QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888,
                    )
                    img = img.scaled(*thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    img.save(str(preview_path))
                    return img
                except Exception:
                    continue

    # Handle PDF directly (for one-shot comics)
    if comic_path.is_file() and comic_path.suffix.lower() == ".pdf" and fitz:
        try:
            doc = fitz.open(str(comic_path))
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=96)
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888,
            )
            img = img.scaled(*thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img.save(str(preview_path))
            return img
        except Exception:
            pass

    return QImage(thumb_size[0], thumb_size[1], QImage.Format_RGB32)


def get_preview_path(comic_path: Path, root: Path) -> Path:
    """
    Return the corresponding preview image path in a central preview folder,
    preserving the relative directory structure of the comic.
    """
    rel = comic_path.relative_to(root)
    preview_base = Path.home() / ".comic_reader_previews"
    if comic_path.is_dir():
        preview_file = preview_base / rel / "preview.jpg"
    else:
        preview_file = preview_base / rel.parent / "preview.jpg"
    return preview_file


def save_custom_preview(comic_path: Path, root: Path, img_path: Path):
    """
    Save a user-specified preview image to the centralized preview directory.
    Ensures directory creation and file copy.
    """
    if not img_path.is_file():
        raise ValueError(f"Selected preview path is not a valid file: {img_path}")

    preview_path = get_preview_path(comic_path, root)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    copyfile(str(img_path), str(preview_path))


def load_and_scale_qimage(img_path: Path, max_size: tuple[int, int]) -> QImage:
    """
    Load an image from disk and scale it to fit within max_size while preserving aspect ratio.
    """
    image = Image.open(img_path)
    image = image.resize(max_size, Image.Resampling.LANCZOS)
    qimg = QImage(image.tobytes(), image.width, image.height, QImage.Format_RGB888)
    return qimg