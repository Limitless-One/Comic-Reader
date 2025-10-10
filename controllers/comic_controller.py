from __future__ import annotations
import json
import shlex
from pathlib import Path
from typing import List, Optional, Dict, Any, Set

from PyQt5.QtCore import QObject, QSettings, QTimer, pyqtSlot, QThreadPool
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from models.comic_model import ComicLibrary, ComicState
from views.application_window import ApplicationWindow
from views.library_manager import LibraryManagerDialog
from views.metadata_editor import MetadataEditorDialog
from views.settings_dialog import SettingsDialog
from utils.images import save_custom_preview
from utils.paths import get_base_data_dir
import sys


class ComicController(QObject):
    ORG_NAME = "PyComicReader"
    APP_NAME = "PyComicReader"
    SETTINGS_ROOTS = "library_roots"
    SETTINGS_GEOMETRY = "main_window_geometry"
    SETTINGS_DARK_MODE = "dark_mode"
    SETTINGS_SENSITIVITY = "classification_sensitivity"
    SETTINGS_DEFAULT_ZOOM = "default_zoom_index"

    def __init__(self):
        super().__init__()
        self.settings = QSettings(self.ORG_NAME, self.APP_NAME)
        self.threadpool = QThreadPool.globalInstance()
        print(f"[INFO] Max threads: {self.threadpool.maxThreadCount()}")

        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(2500)
        self.save_timer.timeout.connect(self._perform_save)

        roots = self._load_or_prompt_roots()
        self.library = ComicLibrary(roots)
        self.apply_settings_to_model()

        self.current_path_parts: List[str] = []
        self.current_comic_key: Optional[str] = None
        self._chapter_sort_key, self._sort_rev = "name", False
        self.dark_mode = self.settings.value(self.SETTINGS_DARK_MODE, False, type=bool)

        self.window = ApplicationWindow(controller=self)
        self.window.toggle_dark_mode(self.dark_mode)
        self._restore_geometry()

        self._wire_signals()
        self._refresh_library_view()

        self.window.show_library()
        self.window.show()

    def _wire_signals(self):
        lv = self.window.library_view
        cv = self.window.chapter_list_view
        rv = self.window.reader_view

        self.window.dark_mode_toggled.connect(self._toggle_dark_mode)
        self.window.settings_requested.connect(self._open_settings)
        self.window.closing.connect(self._on_window_close)

        lv.item_selected.connect(self._on_library_item_selected)
        lv.back_requested.connect(self._go_up)
        lv.manage_library_requested.connect(self._open_library_manager)
        lv.favorite_toggled.connect(self._toggle_favorite)
        lv.search_updated.connect(self._on_search_updated)
        lv.settings_requested.connect(self._open_settings)
        lv.theme_toggled.connect(self._toggle_dark_mode)

        cv.chapter_selected.connect(self._open_chapter)
        cv.bookmark_toggled.connect(self._toggle_bookmark)
        cv.reset_requested.connect(self._reset_progress)
        cv.resume_requested.connect(self._resume_reading)
        cv.sort_changed.connect(self._sort_chapters)
        cv.back_to_library.connect(self.window.show_library)
        cv.change_preview_requested.connect(self._change_preview)
        cv.favorite_toggled.connect(self._toggle_favorite)
        cv.edit_metadata_requested.connect(self._open_metadata_editor)
        cv.breadcrumb_clicked.connect(self._on_breadcrumb_clicked)

        rv.back_to_chapters.connect(self._return_from_reader)
        rv.chapter_requested.connect(self._open_chapter)
        rv.page_changed.connect(self._update_current_page)

    def _get_current_rel_path(self) -> str:
        return "/".join(self.current_path_parts)

    def _refresh_library_view(self, search_term: str = "", deep_search: bool = False):
        rel_path = self._get_current_rel_path()

        if deep_search and search_term:
            # CORRECTION 1: Refined deep search to only show top-level matches.
            all_comics = self.library.get_all_comics()

            # 1. Find all comics and folders that match the search term.
            matching_comic_paths = {
                c.path for c in all_comics if self._matches_search(c, search_term)
            }

            matching_folder_paths = set()
            try:
                for root in self.library.roots:
                    for path in root.rglob(f"*{search_term}*"):
                        if path.is_dir():
                            matching_folder_paths.add(path)
            except Exception as e:
                print(f"[ERROR] Deep search folder glob failed: {e}")

            # 2. Combine all matching paths and find the top-level ones.
            all_paths = matching_comic_paths.union(matching_folder_paths)
            # Sort by path depth to ensure parents are processed before children.
            sorted_paths = sorted(list(all_paths), key=lambda p: len(p.parts))

            final_paths = set()
            for path in sorted_paths:
                # If a parent of this path is already in our final list, skip this path.
                if not any(parent in final_paths for parent in path.parents):
                    final_paths.add(path)

            # 3. Separate the final paths back into comics and folders for the view.
            comic_results = [p for p in final_paths if p in matching_comic_paths]
            folder_results = [p for p in final_paths if p not in matching_comic_paths]

            self.window.library_view.populate(
                "Search Results", folder_results, comic_results, self.library.roots
            )
        else:
            folders, comics = self.library.list_dir(rel_path)
            if search_term:
                search_lower = search_term.lower()
                folders = [f for f in folders if search_lower in f.name.lower()]
                comics = [c for c in comics if search_lower in c.name.lower()]

            self.window.library_view.populate(
                rel_path, folders, comics, self.library.roots
            )

    def _on_library_item_selected(self, path: Path, is_comic: bool):
        if is_comic:
            self._open_comic(path)
        else:
            self._enter_folder(path)

    def _enter_folder(self, path: Path):
        for root in self.library.roots:
            if root == path or root in path.parents:
                self.current_path_parts = list(path.relative_to(root).parts)
                self._refresh_library_view()
                return
        if path in self.library.roots:
            self.current_path_parts = []
            self._refresh_library_view()

    def _go_up(self):
        if self.window.library_view.is_deep_search_active():
            self.window.library_view.clear_search()  # Exit search results view
        elif self.current_path_parts:
            self.current_path_parts.pop()
            self._refresh_library_view()

    def _open_comic(self, path: Path):
        self.window.reader_view.reset_zoom_to_default()
        key = self.library._get_comic_key_from_path(path)
        if not key:
            return

        self.current_comic_key = key
        comic = self.library.get_comic(key)

        if not comic:
            QMessageBox.warning(self.window, "Error", f"Could not load comic: {path.name}")
            return

        if len(comic.chapters) == 1 and not comic.path.is_dir():
            only_key = next(iter(comic.chapters))
            self._open_chapter(only_key)
            return

        self._chapter_sort_key, self._sort_rev = "name", False
        self._update_chapter_list(comic)
        self.window.show_chapters()

    def _update_chapter_list(self, comic: ComicState):
        chapters = comic.sorted_chapters(self._chapter_sort_key, self._sort_rev)
        self.window.chapter_list_view.load_chapters(comic, chapters, self.current_path_parts)

    def _sort_chapters(self, key: str, reverse: bool):
        self._chapter_sort_key, self._sort_rev = key, reverse
        if comic := self.library.get_comic(self.current_comic_key):
            self._update_chapter_list(comic)

    def _open_chapter(self, chapter_key: str, start_page: int = 0):
        if not self.current_comic_key: return
        comic = self.library.get_comic(self.current_comic_key)
        if not comic or chapter_key not in comic.chapters: return

        self.library.mark_read(self.current_comic_key, chapter_key)
        self.save_timer.start()

        chap = comic.chapters[chapter_key]
        ordered = comic.sorted_chapters(self._chapter_sort_key, self._sort_rev)
        self.window.reader_view.load_chapter(chap, ordered, start_page)
        self.window.show_reader()

    def _resume_reading(self):
        comic = self.library.get_comic(self.current_comic_key)
        if comic and comic.last_read_chapter in comic.chapters:
            self._open_chapter(comic.last_read_chapter, comic.last_read_page)

    def _return_from_reader(self):
        if comic := self.library.get_comic(self.current_comic_key):
            self._update_chapter_list(comic)
            self.window.show_chapters()
        else:
            self.window.show_library()

    def _update_current_page(self, page_index: int):
        if comic := self.library.get_comic(self.current_comic_key):
            if comic.last_read_page != page_index:
                comic.last_read_page = page_index
                self.save_timer.start()

    @pyqtSlot(list)
    def _on_breadcrumb_clicked(self, path_parts: List[str]):
        """Navigates to a folder path selected from the breadcrumb trail."""
        self.current_path_parts = path_parts
        self._refresh_library_view()
        self.window.show_library()

    def _toggle_bookmark(self, chapter_key: str):
        self.library.toggle_bookmark(self.current_comic_key, chapter_key)
        self.save_timer.start()
        if comic := self.library.get_comic(self.current_comic_key):
            self._update_chapter_list(comic)

    def _toggle_favorite(self, comic_key: Optional[str] = None):
        key = comic_key or self.current_comic_key
        if not key: return

        self.library.toggle_favorite(key)
        self.save_timer.start()

        comic = self.library.get_comic(key)
        if not comic: return

        self.window.library_view.update_comic_favorite_state(key, comic.favorite)
        if key == self.current_comic_key:
            self.window.chapter_list_view.update_favorite_state(comic.favorite)

    def _reset_progress(self):
        self.library.reset_progress(self.current_comic_key)
        self.save_timer.start()
        if comic := self.library.get_comic(self.current_comic_key):
            self._update_chapter_list(comic)

    def _open_library_manager(self):
        dialog = LibraryManagerDialog(self.library.roots, self.window)
        if dialog.exec_():
            new_roots = dialog.get_roots()
            if new_roots != self.library.roots:
                self.settings.setValue(
                    self.SETTINGS_ROOTS, json.dumps([str(p) for p in new_roots])
                )
                self.library = ComicLibrary(new_roots)
                self.apply_settings_to_model()
                self.current_path_parts.clear()
                self._refresh_library_view()

    def _open_metadata_editor(self):
        if not self.current_comic_key: return
        comic = self.library.get_comic(self.current_comic_key)
        if not comic: return

        dialog = MetadataEditorDialog(comic.metadata, self.window)
        if dialog.exec_():
            new_metadata = dialog.get_metadata()
            self.library.update_metadata(self.current_comic_key, new_metadata)
            self.save_timer.start()
            self._update_chapter_list(comic)

    def _open_settings(self):
        dialog = SettingsDialog(self.settings, self.window)
        if dialog.exec_():
            self.apply_settings_to_model()
            if self.window.stack.currentWidget() == self.window.library_view:
                self._refresh_library_view()
            if self.window.stack.currentWidget() == self.window.reader_view:
                self.window.reader_view.apply_settings()

    def _change_preview(self):
        if not self.current_comic_key: return
        comic = self.library.get_comic(self.current_comic_key)
        if not comic: return

        file_path, _ = QFileDialog.getOpenFileName(
            self.window, "Select Preview Image", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if file_path:
            save_custom_preview(comic.path, Path(file_path))
            self._update_chapter_list(comic)
            self.window.library_view.refresh_item_preview(self.current_comic_key)

    def _load_or_prompt_roots(self) -> List[Path]:
        try:
            saved_str = self.settings.value(self.SETTINGS_ROOTS, "[]")
            saved_paths = [Path(p) for p in json.loads(saved_str)]
            existing_paths = [p for p in saved_paths if p.exists()]
            if existing_paths:
                return existing_paths
        except (json.JSONDecodeError, TypeError):
            pass

        QMessageBox.information(
            None, "Welcome", "Please select a folder containing your comics to start."
        )
        folder = QFileDialog.getExistingDirectory(None, "Select Comics Folder")
        if not folder:
            sys.exit("No folder selected.")

        roots = [Path(folder)]
        self.settings.setValue(self.SETTINGS_ROOTS, json.dumps([str(p) for p in roots]))
        return roots

    def _toggle_dark_mode(self, is_dark):
        self.dark_mode = is_dark
        self.settings.setValue(self.SETTINGS_DARK_MODE, self.dark_mode)
        self.window.toggle_dark_mode(is_dark)

    def _on_search_updated(self, text: str, deep_search: bool):
        self._refresh_library_view(search_term=text, deep_search=deep_search)

    def _matches_search(self, comic: ComicState, query: str) -> bool:
        query_lower = query.lower()
        # Include comic name and full path for simple text matching
        simple_search_target = f"{comic.display_name} {comic.path.as_posix()}".lower()

        # Check for advanced query syntax (e.g., key:value)
        try:
            parts = shlex.split(query_lower)
        except ValueError:
            parts = query_lower.split()

        has_advanced_filter = any(":" in part for part in parts)
        if not has_advanced_filter:
            # Simple search: all parts of the query must be present
            return all(part in simple_search_target for part in parts)

        # Advanced search logic
        for part in parts:
            if ":" in part:
                key, val = part.split(":", 1)
                is_negated = key.startswith("-")
                if is_negated:
                    key = key[1:]

                # Check metadata for a match
                metadata_val = str(comic.metadata.get(key, "")).lower()
                is_match = val in metadata_val

                if (is_negated and is_match) or (not is_negated and not is_match):
                    return False  # Condition failed
            else:
                # Regular text part must also match
                if part not in simple_search_target:
                    return False

        return True  # All conditions passed

    def apply_settings_to_model(self):
        sensitivity = self.settings.value(self.SETTINGS_SENSITIVITY, 0.8, type=float)
        self.library.set_classification_sensitivity(sensitivity)

    @pyqtSlot()
    def _perform_save(self):
        self.library.save()

    def _on_window_close(self):
        self.settings.setValue(self.SETTINGS_GEOMETRY, self.window.saveGeometry())
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._perform_save()
        self.threadpool.clear()
        self.threadpool.waitForDone(1000)

    def _restore_geometry(self):
        geometry = self.settings.value(self.SETTINGS_GEOMETRY)
        if isinstance(geometry, bytes):
            self.window.restoreGeometry(geometry)

