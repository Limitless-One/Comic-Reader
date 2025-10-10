from __future__ import annotations
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from natsort import natsorted

from utils.config import (
    SUPPORTED_DOC_EXTS,
    SUPPORTED_IMAGE_EXTS,
    HIDDEN_PREFIX,
)
from utils.paths import get_state_file_path

# --- Classification Logic ---

MIN_CHAPTER_IMAGES = 1
IMPURE_FOLDER_THRESHOLD = 0.8
SUPPORTED_CHAPTER_EXTS = SUPPORTED_DOC_EXTS | {".cbz", ".epub"}


def _is_chapter_folder(path: Path, impure_threshold: float) -> bool:
    """
    Checks if a directory qualifies as a single chapter (a folder of images).
    Rule: Contains images, NO subfolders, and NO other chapter-type files (like .cbz).
    FIXED: Also ignores empty directories and handles non-image chapter files correctly.
    """
    if not path.is_dir():
        return False

    image_count = 0
    other_file_count = 0

    try:
        # Perform a single pass over children for efficiency.
        children = list(path.iterdir())

        # A folder is not a chapter if it's effectively empty (contains no visible files/folders).
        if not any(not item.name.startswith(HIDDEN_PREFIX) for item in children):
            return False

        for child in children:
            if child.name.startswith(HIDDEN_PREFIX):
                continue

            # A chapter cannot contain subfolders or other standalone chapter-type files.
            if child.is_dir():
                return False
            if child.suffix.lower() in SUPPORTED_CHAPTER_EXTS:
                return False

            # Tally supported image files vs other non-chapter files.
            if child.is_file():
                if child.suffix.lower() in SUPPORTED_IMAGE_EXTS:
                    image_count += 1
                else:
                    other_file_count += 1
    except OSError:
        return False

    total_files = image_count + other_file_count
    # A chapter must contain a minimum number of images.
    if image_count < MIN_CHAPTER_IMAGES:
        return False

    return (image_count / total_files) >= impure_threshold


def is_chapter(path: Path, impure_threshold: float) -> bool:
    """Checks if a path is a chapter (file or folder)."""
    if path.suffix.lower() in SUPPORTED_CHAPTER_EXTS:
        return True
    return _is_chapter_folder(path, impure_threshold)


def _analyze_directory_contents(
        path: Path, impure_threshold: float
) -> Tuple[List[Path], List[Path]]:
    """
    Analyzes a directory's immediate children to classify them.
    Returns two lists: (direct_chapters, sub_folders_that_are_not_chapters).
    FIXED: Now ignores empty subdirectories.
    """
    direct_chapters = []
    navigable_sub_folders = []

    try:
        for child in path.iterdir():
            if child.name.startswith(HIDDEN_PREFIX):
                continue

            if is_chapter(child, impure_threshold):
                direct_chapters.append(child)
            elif child.is_dir():
                # Check if the directory is effectively empty before adding it.
                try:
                    is_empty = not any(not item.name.startswith(HIDDEN_PREFIX) for item in child.iterdir())
                    if not is_empty:
                        navigable_sub_folders.append(child)
                except OSError:
                    # Cannot access, treat as non-navigable.
                    pass
    except OSError:
        pass

    return direct_chapters, navigable_sub_folders


# --- Data Classes ---


@dataclass
class ChapterState:
    path: Path
    read: bool = False
    bookmarked: bool = False
    last_opened: float = 0.0

    @property
    def display_name(self) -> str:
        return self.path.name if self.path.is_dir() else self.path.stem

    def mark_read(self):
        self.read = True
        self.last_opened = time.time()

    def toggle_bookmark(self):
        self.bookmarked = not self.bookmarked


@dataclass
class ComicState:
    path: Path
    metadata: Dict[str, Any] = field(default_factory=dict)
    chapters: Dict[str, ChapterState] = field(default_factory=dict)
    last_read_chapter: Optional[str] = None
    last_read_page: int = 0
    favorite: bool = False

    @property
    def display_name(self) -> str:
        return self.path.name

    def sorted_chapters(
            self, by: str = "name", reverse: bool = False
    ) -> List[ChapterState]:
        if by == "date":
            key_fn = lambda ch: ch.path.stat().st_mtime
        else:
            key_fn = lambda ch: ch.display_name
        return natsorted(self.chapters.values(), key=key_fn, reverse=reverse)


# --- Library Model ---


class ComicLibrary:
    def __init__(self, roots: List[Path]):
        self.roots = [Path(r) for r in roots]
        self.state_file = get_state_file_path()
        self.comics: Dict[str, ComicState] = {}
        self.impure_threshold = IMPURE_FOLDER_THRESHOLD

        self._build_full_comic_list()
        self._load_state()

    def is_path_a_chapter(self, path: Path) -> bool:
        """Convenience method to check if a path is a chapter using current settings."""
        return is_chapter(path, self.impure_threshold)

    def set_classification_sensitivity(self, threshold: float):
        self.impure_threshold = max(0.1, min(1.0, threshold))

    def _get_comic_key_from_path(self, path: Path) -> Optional[str]:
        for root in self.roots:
            if root == path or root in path.parents:
                try:
                    return path.relative_to(root).as_posix()
                except ValueError:
                    continue
        return None

    def _get_path_from_comic_key(self, key: str) -> Optional[Path]:
        for root in self.roots:
            if (full_path := root / key).exists():
                return full_path
        return None

    def _build_full_comic_list(self):
        """
        Scans all library roots ONCE and populates the self.comics dictionary.
        This is the new indexing mechanism to make deep search fast.
        """
        print("[INFO] Building comic library index from filesystem...")
        start_time = time.time()
        for root in self.roots:
            try:
                for entry in root.rglob("*"):
                    if entry.name.startswith(HIDDEN_PREFIX):
                        continue

                    if not entry.is_dir():
                        continue

                    chapters, _ = _analyze_directory_contents(entry, self.impure_threshold)
                    if chapters:
                        key = self._get_comic_key_from_path(entry)
                        if key and key not in self.comics:
                            cs = ComicState(path=entry)
                            for chapter_path in chapters:
                                cs.chapters[chapter_path.name] = ChapterState(chapter_path)
                            self.comics[key] = cs
            except OSError as e:
                print(f"[WARN] Could not scan {root}: {e}")
        end_time = time.time()
        print(f"[INFO] Index built in {end_time - start_time:.2f}s. Found {len(self.comics)} comics.")

    def get_all_comics(self) -> List[ComicState]:
        """Returns the pre-built list of comics from memory."""
        return list(self.comics.values())

    def list_dir(self, rel_path: str = "") -> Tuple[List[Path], List[Path]]:
        if not rel_path:
            folders, comics = set(), set()
            for root in self.roots:
                root_folders, root_comics = self._scan_single_dir(root)
                folders.update(root_folders)
                comics.update(root_comics)
            return natsorted(list(folders), key=lambda p: p.name), natsorted(list(comics), key=lambda p: p.name)

        current_path = self._get_path_from_comic_key(rel_path)
        if current_path and current_path.is_dir():
            return self._scan_single_dir(current_path)

        return [], []

    def _scan_single_dir(self, path: Path) -> Tuple[List[Path], List[Path]]:
        """
        FIXED: This method now correctly handles mixed directories without duplication.
        A directory is classified based on its children. It no longer adds itself
        to its own list of comics, preventing the redundant virtual comic entry.
        """
        folders, comics = [], []
        try:
            entries = natsorted(
                [p for p in path.iterdir() if not p.name.startswith(HIDDEN_PREFIX)],
                key=lambda p: p.name,
            )
        except OSError:
            return [], []

        for entry in entries:
            if not entry.is_dir():
                continue  # We only classify directories here

            # Analyze the child directory 'entry'
            child_chapters, child_sub_folders = _analyze_directory_contents(
                entry, self.impure_threshold
            )

            # If the entry contains its own chapters, list it as a comic.
            if child_chapters:
                comics.append(entry)

            # If the entry contains sub-folders, it's a navigable folder.
            # A "mixed" directory will be added to both lists, creating the virtual split.
            if child_sub_folders:
                folders.append(entry)

        return folders, comics

    def get_comic(self, rel_key: str) -> Optional[ComicState]:
        if rel_key in self.comics:
            # Make sure chapters are up-to-date if fetched from cache
            comic = self.comics[rel_key]
            current_chapters, _ = _analyze_directory_contents(comic.path, self.impure_threshold)
            current_chapter_names = {c.name for c in current_chapters}
            cached_chapter_names = set(comic.chapters.keys())

            if current_chapter_names != cached_chapter_names:
                # Rescan chapters if they've changed on disk
                comic.chapters.clear()
                for chapter_path in current_chapters:
                    comic.chapters[chapter_path.name] = ChapterState(path=chapter_path)
            return comic

        abs_path = self._get_path_from_comic_key(rel_key)
        if not abs_path:
            if rel_key in self.comics:
                del self.comics[rel_key]
            return None

        cs = ComicState(path=abs_path)
        chapters, _ = _analyze_directory_contents(abs_path, self.impure_threshold)

        # Special case for single-file comics like a lone .cbz file
        if not chapters and is_chapter(abs_path, self.impure_threshold):
            chapters = [abs_path]

        for chapter_path in chapters:
            cs.chapters[chapter_path.name] = ChapterState(path=chapter_path)

        if cs.chapters:
            self.comics[rel_key] = cs
        return cs if cs.chapters else None

    def _load_state(self):
        if not self.state_file.exists():
            return
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[ERROR] Failed to parse state.json: {e}")
            return

        for key, blob in raw.get("comics", {}).items():
            comic = self.get_comic(key)
            if not comic:
                continue

            comic.last_read_chapter = blob.get("last_read_chapter")
            comic.last_read_page = blob.get("last_read_page", 0)
            comic.favorite = blob.get("favorite", False)
            comic.metadata = blob.get("metadata", {})

            for c_name, info in blob.get("chapters", {}).items():
                if c_name in comic.chapters:
                    ch = comic.chapters[c_name]
                    ch.read = info.get("read", False)
                    ch.bookmarked = info.get("bookmarked", False)
                    ch.last_opened = info.get("last_opened", 0.0)

    def save(self):
        data = {"comics": {}}
        for key, c in self.comics.items():
            data["comics"][key] = {
                "last_read_chapter": c.last_read_chapter,
                "last_read_page": c.last_read_page,
                "favorite": c.favorite,
                "metadata": c.metadata,
                "chapters": {
                    n: {
                        "read": ch.read,
                        "bookmarked": ch.bookmarked,
                        "last_opened": ch.last_opened,
                    }
                    for n, ch in c.chapters.items()
                },
            }
        try:
            self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print("[INFO] Application state saved.")
        except OSError as e:
            print(f"[ERROR] ComicLibrary save error: {e}")

    def mark_read(self, comic_key: str, chap_key: str):
        if comic := self.comics.get(comic_key):
            if chap := comic.chapters.get(chap_key):
                chap.mark_read()
                comic.last_read_chapter = chap_key
                comic.last_read_page = 0

    def toggle_bookmark(self, comic_key: str, chap_key: str):
        if (comic := self.comics.get(comic_key)) and (
                chap := comic.chapters.get(chap_key)
        ):
            chap.toggle_bookmark()

    def toggle_favorite(self, comic_key: str):
        if comic := self.comics.get(comic_key):
            comic.favorite = not comic.favorite

    def reset_progress(self, comic_key: str):
        if comic := self.comics.get(comic_key):
            for ch in comic.chapters.values():
                ch.read = False
                ch.last_opened = 0.0
            comic.last_read_chapter = None
            comic.last_read_page = 0

    def update_metadata(self, comic_key: str, new_metadata: Dict[str, Any]):
        if comic := self.comics.get(comic_key):
            comic.metadata = new_metadata
