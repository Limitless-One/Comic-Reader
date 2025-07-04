"""
main.py
-------
Entry point for the Comic Reader application.
Initializes and launches the main controller with persistent folder selection.
"""

from __future__ import annotations
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox, QWidget

# Local import AFTER Qt so sys.path is ready
from controllers import ComicController


def choose_root(parent: QWidget | None) -> Path | None:
    """Show a modal folder‑picker and return the selected path or None."""
    folder = QFileDialog.getExistingDirectory(parent, "Select Comics Folder")
    return Path(folder) if folder else None


def main() -> None:
    # Create the application instance
    app = QApplication(sys.argv)

    ctrl: ComicController | None = None
    try:
        # Load last used folder from settings, or prompt if missing
        setting_keys = (ComicController.ORG, ComicController.APP, "last_root")
        settings = QSettings(*setting_keys[:2])
        root = Path(settings.value(setting_keys[2])) if settings.value(setting_keys[2]) else None

        if root is None or not root.exists():
            # Prompt user to select comics folder
            root = choose_root(None)
            if root is None:
                # User canceled — exit cleanly
                QMessageBox.information(None, "Comic Reader", "No folder selected.")
                sys.exit(0)
            settings.setValue(setting_keys[2], str(root))

        # Build the main controller (constructs and displays the UI)
        ctrl = ComicController(root)

    except Exception as exc:
        # Handle unexpected errors with a visible alert
        QMessageBox.critical(None, "Comic Reader – Error", str(exc))
        raise

    # Start the Qt application loop
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
