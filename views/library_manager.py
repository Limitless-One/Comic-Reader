from pathlib import Path
from typing import List

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QFileDialog, QAbstractItemView, QListWidgetItem
)
from PyQt5.QtCore import Qt


class LibraryManagerDialog(QDialog):
    """A dialog to add, remove, and view library root folders."""

    def __init__(self, current_roots: List[Path], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Library Folders")
        self.setMinimumSize(600, 400)

        self.list_widget = QListWidget()
        for root in current_roots:
            item = QListWidgetItem(str(root))
            item.setData(Qt.UserRole, root)
            self.list_widget.addItem(item)

        self.add_button = QPushButton("Add Folder...")
        self.remove_button = QPushButton("Remove Selected")
        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Cancel")

        self.add_button.clicked.connect(self._add_folder)
        self.remove_button.clicked.connect(self._remove_folder)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.list_widget)
        main_layout.addLayout(button_layout)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Comics Folder")
        if folder:
            path = Path(folder)
            # Avoid adding duplicates
            if not self.list_widget.findItems(str(path), Qt.MatchExactly):
                item = QListWidgetItem(str(path))
                item.setData(Qt.UserRole, path)
                self.list_widget.addItem(item)

    def _remove_folder(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def get_roots(self) -> List[Path]:
        """Returns the final list of root paths."""
        roots = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            roots.append(item.data(Qt.UserRole))
        return roots
