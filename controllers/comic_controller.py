from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from models import ComicLibrary, ComicState
from utils import chapter_is_image_folder, get_preview_path, save_custom_preview
from views.application_window import ApplicationWindow


class ComicController:
    ORG = "ComicReader"
    APP = "Settings"

    def __init__(self, root: Optional[Path] = None):
        self.settings = QSettings(self.ORG, self.APP)
        start_root = Path(root) if root else self._load_or_prompt_root()

        self.library = ComicLibrary(start_root)
        self.current_path: List[str] = []
        self.current_comic_key: Optional[str] = None
        self._chapter_sort_key, self._sort_rev = "name", False
        self.dark_mode = False

        self.window = ApplicationWindow(controller=self)
        self._wire_signals()
        self._refresh_library_view()
        self.window.show_library()
        self.window.show()

    def _wire_signals(self):
        lv = self.window.library_view
        cv = self.window.chapter_list_view
        rv = self.window.reader_view

        lv.folder_selected.connect(self._enter_folder)
        lv.comic_selected.connect(self._open_comic)
        lv.back_requested.connect(self._go_up)
        lv.root_change_requested.connect(self._choose_new_root)
        lv.favorite_toggled.connect(self._toggle_favorite_from_library)

        cv.chapter_selected.connect(self._open_chapter)
        cv.bookmark_toggled.connect(self._toggle_bookmark)
        cv.reset_requested.connect(self._reset_progress)
        cv.resume_requested.connect(self._resume_reading)
        cv.sort_changed.connect(self._sort_chapters)
        cv.back_to_library.connect(self.window.show_library)

        cv.change_preview_requested.connect(self._change_preview)
        cv.favorite_toggled.connect(self._toggle_favorite_from_chapter)

        rv.back_to_chapters.connect(self._return_from_reader)
        rv.chapter_requested.connect(self._open_chapter)

    def _rel_path(self) -> str:
        return "/".join(self.current_path)

    def _refresh_library_view(self):
        rel = self._rel_path()
        folders, comics = self.library.list_dir(rel)
        self.window.library_view.populate(rel, folders, comics, self.library.root)

    def _enter_folder(self, name: str):
        self.current_path.append(name)
        self._refresh_library_view()

    def _go_up(self):
        if self.current_path:
            self.current_path.pop()
            self._refresh_library_view()

    def _open_comic(self, name: str):
        self.current_comic_key = f"{self._rel_path()}/{name}".lstrip("/")
        comic = self.library.get_comic(self.current_comic_key)

        if len(comic.chapters) == 1:
            only_key = next(iter(comic.chapters))
            if only_key.lower().endswith(".pdf"):
                chap = comic.chapters[only_key]
                ordered = comic.sorted_chapters(self._chapter_sort_key, self._sort_rev)
                self.window.reader_view.load_chapter(chap, ordered)
                self.window.show_reader()
                return

        self._chapter_sort_key, self._sort_rev = "name", False
        self._update_chapter_list(comic)
        self.window.show_chapters()

    def _update_chapter_list(self, comic: ComicState):
        chapters = comic.sorted_chapters(self._chapter_sort_key, self._sort_rev)
        self.window.chapter_list_view.load_chapters(comic, chapters, self.library.root)

    def _sort_chapters(self, key: str, reverse: bool):
        self._chapter_sort_key, self._sort_rev = key, reverse
        comic = self.library.get_comic(self.current_comic_key)
        self._update_chapter_list(comic)

    def _open_chapter(self, chapter_key: str):
        comic = self.library.get_comic(self.current_comic_key)
        chap = comic.chapters[chapter_key]

        if chap.path.is_dir() and not chapter_is_image_folder(chap.path):
            self.current_path = [p for p in self.current_comic_key.split("/") if p]
            self._open_comic(chapter_key)
            return

        self.library.mark_read(self.current_comic_key, chapter_key)
        ordered = comic.sorted_chapters(self._chapter_sort_key, self._sort_rev)
        self.window.reader_view.load_chapter(chap, ordered)
        self.window.show_reader()

    def _resume_reading(self):
        comic = self.library.get_comic(self.current_comic_key)
        if comic.last_read_chapter and comic.last_read_chapter in comic.chapters:
            chap = comic.chapters[comic.last_read_chapter]
            ordered = comic.sorted_chapters(self._chapter_sort_key, self._sort_rev)
            self.window.reader_view.load_chapter(chap, ordered)
            self.window.show_reader()

    def _toggle_bookmark(self, chapter_key: str):
        self.library.toggle_bookmark(self.current_comic_key, chapter_key)
        comic = self.library.get_comic(self.current_comic_key)
        self._update_chapter_list(comic)

    def _reset_progress(self):
        self.library.reset_progress(self.current_comic_key)
        comic = self.library.get_comic(self.current_comic_key)
        self._update_chapter_list(comic)

    def _return_from_reader(self):
        comic = self.library.get_comic(self.current_comic_key)
        self._update_chapter_list(comic)
        self.window.show_chapters()

    def _choose_new_root(self):
        new_dir = QFileDialog.getExistingDirectory(self.window, "Choose Comics Folder")
        if new_dir:
            self.settings.setValue("last_root", new_dir)
            self.library = ComicLibrary(Path(new_dir))
            self.current_path.clear()
            self._refresh_library_view()
            self.window.show_library()

    def _load_or_prompt_root(self) -> Path:
        saved = self.settings.value("last_root")
        if saved and Path(saved).exists():
            return Path(saved)
        folder = QFileDialog.getExistingDirectory(None, "Select Comics Folder")
        if not folder:
            QMessageBox.critical(None, "Comic Reader", "No folder selected. Exiting.")
            raise SystemExit(1)
        self.settings.setValue("last_root", folder)
        return Path(folder)

    def _change_preview(self):
        comic = self.library.get_comic(self.current_comic_key)

        # Force user to select a valid image file
        file_dialog_result = QFileDialog.getOpenFileName(
            self.window,
            "Select New Preview Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )

        if not file_dialog_result or not file_dialog_result[0]:
            return  # Cancelled

        img_path = Path(file_dialog_result[0])

        # Explicitly ensure the selected file is actually a file
        if not img_path.is_file():
            QMessageBox.warning(
                self.window,
                "Invalid Selection",
                f"Selected path is not a file:\n{img_path}"
            )
            return

        try:
            # Save preview image
            save_custom_preview(comic.path, self.library.root, img_path)
            self._update_chapter_list(comic)
        except Exception as e:
            QMessageBox.critical(
                self.window,
                "Preview Save Failed",
                f"An error occurred while saving the preview:\n{e}"
            )

    def _toggle_favorite_from_library(self, comic_name: str):
        """Handle favorite toggle from library view"""
        # Get the full comic key
        comic_key = f"{self._rel_path()}/{comic_name}".lstrip("/")
        comic = self.library.get_comic(comic_key)

        # Toggle favorite state
        comic.favorite = not comic.favorite
        self.library.save()

        # Update library view to reflect the change
        self.window.library_view.update_comic_favorite(comic_name, comic.favorite)

        # Update chapter view if we're viewing this comic
        if self.current_comic_key == comic_key:
            self.window.chapter_list_view.update_favorite_state(comic.favorite)

    def _toggle_favorite_from_chapter(self):
        """Handle favorite toggle from chapter view"""
        comic = self.library.get_comic(self.current_comic_key)
        comic.favorite = not comic.favorite
        self.library.save()

        # Update chapter view button (already handled by the view, but ensure consistency)
        self.window.chapter_list_view.update_favorite_state(comic.favorite)

        # Update library view if this comic is visible
        comic_name = self.current_comic_key.split("/")[-1]
        self.window.library_view.update_comic_favorite(comic_name, comic.favorite)