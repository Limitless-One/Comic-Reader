from typing import Dict, Any
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView
)

class MetadataEditorDialog(QDialog):
    """A dialog for editing comic metadata as key-value pairs."""

    def __init__(self, metadata: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Comic Metadata")
        self.setMinimumSize(500, 400)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Tag", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        for key, value in metadata.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.table.setItem(row, 1, QTableWidgetItem(str(value)))

        self.add_row_btn = QPushButton("Add Tag")
        self.remove_row_btn = QPushButton("Remove Selected Tag")
        self.ok_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")

        self.add_row_btn.clicked.connect(self._add_row)
        self.remove_row_btn.clicked.connect(self._remove_row)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_row_btn)
        button_layout.addWidget(self.remove_row_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.ok_btn)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.table)
        main_layout.addLayout(button_layout)

    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)

    def _remove_row(self):
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)

    def get_metadata(self) -> Dict[str, Any]:
        """Returns the edited metadata."""
        metadata = {}
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            if key_item and key_item.text():
                key = key_item.text().strip()
                value = value_item.text().strip() if value_item else ""
                metadata[key] = value
        return metadata
