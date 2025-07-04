from __future__ import annotations
import json, os, platform, time, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils import chapter_is_image_folder

# ──────────────────────────────────────────── constants & helpers
STATE_FILE_NAME = "state.json"
SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SUPPORTED_DOC_EXTS   = {".pdf"}
PREVIEW_SUFFIXES = ("_preview.jpg", "_preview.jpeg", "_preview.png", "_preview.webp")
HIDDEN_PREFIX    = "."

def _state_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home())) if platform.system() == "Windows" else Path.home() / ".comicreader"
    base.mkdir(parents=True, exist_ok=True)
    return base / STATE_FILE_NAME

def _visible_children(p: Path):
    return [c for c in p.iterdir() if not c.name.startswith(HIDDEN_PREFIX) and not c.name.lower().endswith(PREVIEW_SUFFIXES)]

def _is_image_folder(p: Path):
    return p.is_dir() and _visible_children(p) and all(
        f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTS for f in _visible_children(p)
    )

def _is_chapter(p: Path):
    return (p.is_file() and p.suffix.lower() in SUPPORTED_DOC_EXTS) or _is_image_folder(p)

def _is_preview_img(f: Path):
    return f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE_EXTS

def _is_comic_dir(p: Path):
    kids = _visible_children(p)
    if not kids:
        return True
    has = False
    for k in kids:
        if _is_chapter(k):
            has = True
            continue
        if _is_preview_img(k) or k.is_dir():
            continue
        return False
    return has

# ──────────────────────────────── dataclasses
@dataclass
class ChapterState:
    path: Path
    read: bool = False
    bookmarked: bool = False
    last_opened: float = 0.0

    @property
    def display_name(self):
        return self.path.name if self.path.is_dir() else self.path.stem

    def mark_read(self):
        self.read = True
        self.last_opened = time.time()

    def toggle_bookmark(self):
        self.bookmarked = not self.bookmarked

@dataclass
class ComicState:
    path: Path
    chapters: Dict[str, ChapterState] = field(default_factory=dict)
    last_read_chapter: Optional[str] = None
    favorite: bool = False

    _split_re = re.compile(r'(\d+(?:\.\d+)?)')

    @classmethod
    def _natural_key(cls, title: str):
        clean = title.replace("_", " ").replace("-", " ")
        clean = re.sub(r'\s+', ' ', clean).strip().lower()

        parts = []
        for part in cls._split_re.split(clean):
            if not part:
                continue
            try:
                parts.append((0, float(part)))
            except ValueError:
                parts.append((1, part))
        return parts

    @property
    def display_name(self) -> str:
        return self.path.name

    def sorted_chapters(self, by: str = "name", reverse: bool = False) -> List[ChapterState]:
        if by == "date":
            key_fn = lambda ch: ch.path.stat().st_mtime
        else:
            key_fn = lambda ch: self._natural_key(ch.display_name)
        return sorted(self.chapters.values(), key=key_fn, reverse=reverse)

# ──────────────────────────── ComicLibrary
class ComicLibrary:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.state_file = _state_path()
        self.comics: Dict[str, ComicState] = {}
        self._load_state()

    def list_dir(self, rel: str = "") -> Tuple[List[str], List[str]]:
        here = self.root / rel
        if not here.exists():
            return [], []

        folders, comics = [], []
        for entry in sorted(here.iterdir(), key=lambda p: p.name.lower()):
            nm = entry.name.lower()
            if nm.startswith(HIDDEN_PREFIX) or nm.endswith(PREVIEW_SUFFIXES):
                continue

            if entry.is_file() and entry.suffix.lower() in SUPPORTED_DOC_EXTS:
                comics.append(entry.name)
                continue

            if entry.is_dir():
                if _is_comic_dir(entry):
                    comics.append(entry.name)
                else:
                    folders.append(entry.name)

        return folders, comics

    def get_comic(self, rel: str) -> ComicState:
        if rel not in self.comics:
            self._register_comic(rel)
        return self.comics[rel]

    def _register_comic(self, rel: str):
        abs_path = self.root / rel
        if abs_path.is_file() and abs_path.suffix.lower() in SUPPORTED_DOC_EXTS:
            cs = ComicState(abs_path.parent)
            cs.chapters[abs_path.name] = ChapterState(abs_path)
            self.comics[rel] = cs
            return

        cs = ComicState(abs_path)
        for kid in _visible_children(abs_path):
            if _is_chapter(kid) or kid.is_dir():
                cs.chapters[kid.name] = ChapterState(kid)
        self.comics[rel] = cs

    def _load_state(self):
        if not self.state_file.exists():
            return
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return

        for key, blob in raw.get("comics", {}).items():
            self._register_comic(key)
            comic = self.comics.get(key)
            if not comic:
                continue
            comic.last_read_chapter = blob.get("last_read_chapter")
            comic.favorite = blob.get("favorite", False)
            for c_name, info in blob.get("chapters", {}).items():
                if c_name in comic.chapters:
                    ch = comic.chapters[c_name]
                    ch.read = info.get("read", False)
                    ch.bookmarked = info.get("bookmarked", False)
                    ch.last_opened = info.get("last_opened", 0.0)

    def save(self):
        data = {
            "comics": {
                key: {
                    "last_read_chapter": c.last_read_chapter,
                    "favorite": c.favorite,
                    "chapters": {
                        n: {
                            "read": ch.read,
                            "bookmarked": ch.bookmarked,
                            "last_opened": ch.last_opened,
                        }
                        for n, ch in c.chapters.items()
                    },
                }
                for key, c in self.comics.items()
            }
        }
        try:
            self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as e:
            print("ComicLibrary save error:", e)

    def mark_read(self, comic_key: str, chap_key: str):
        ch = self.comics[comic_key].chapters[chap_key]
        ch.mark_read()
        self.comics[comic_key].last_read_chapter = chap_key
        self.save()

    def toggle_bookmark(self, comic_key: str, chap_key: str):
        self.comics[comic_key].chapters[chap_key].toggle_bookmark()
        self.save()

    def reset_progress(self, comic_key: str):
        for ch in self.comics[comic_key].chapters.values():
            ch.read = False
            ch.last_opened = 0.0
        self.comics[comic_key].last_read_chapter = None
        self.save()
