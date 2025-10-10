import os
import platform
import hashlib
from pathlib import Path
from .config import STATE_FILE_NAME, PREVIEW_CACHE_DIR

def get_base_data_dir() -> Path:
    """Gets the platform-specific application data directory."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        # Linux, macOS
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    app_dir = base / "PyComicReader"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir

def get_state_file_path() -> Path:
    """Gets the absolute path to the state.json file."""
    return get_base_data_dir() / STATE_FILE_NAME

def get_preview_cache_path(comic_path: Path) -> Path:
    """
    Creates a unique, filesystem-safe cache path for a comic's preview.
    Hashing the full path avoids issues with long filenames or special characters.
    """
    # Create a stable hash of the absolute comic path
    hasher = hashlib.md5()
    hasher.update(str(comic_path.resolve()).encode('utf-8'))
    hashed_name = hasher.hexdigest()

    cache_dir = get_base_data_dir() / PREVIEW_CACHE_DIR
    return cache_dir / f"{hashed_name}.jpg"
