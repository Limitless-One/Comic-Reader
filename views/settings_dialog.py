from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox, QDoubleSpinBox,
    QComboBox, QLabel, QGroupBox
)
from PyQt5.QtCore import QSettings

class SettingsDialog(QDialog):
    """A dialog for managing application-wide settings."""

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Application Settings")

        # --- Reader Settings ---
        reader_group = QGroupBox("Reader")
        reader_layout = QFormLayout()

        self.default_zoom_combo = QComboBox()
        zoom_levels = ["25%", "50%", "75%", "100%", "125%", "150%", "175%", "200%"]
        self.default_zoom_combo.addItems(zoom_levels)
        reader_layout.addRow("Default Zoom Level:", self.default_zoom_combo)

        reader_group.setLayout(reader_layout)

        # --- Library Settings ---
        library_group = QGroupBox("Library")
        library_layout = QFormLayout()

        self.sensitivity_spinbox = QDoubleSpinBox()
        self.sensitivity_spinbox.setRange(0.1, 1.0)
        self.sensitivity_spinbox.setSingleStep(0.05)
        self.sensitivity_spinbox.setSuffix(" % images")
        library_layout.addRow(
            "Chapter Folder Sensitivity:", self.sensitivity_spinbox
        )
        library_group.setLayout(library_layout)


        # --- Dialog Buttons ---
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(reader_group)
        main_layout.addWidget(library_group)
        main_layout.addStretch()
        main_layout.addWidget(self.button_box)

        self._load_settings()

    def _load_settings(self):
        """Load current settings into the UI controls."""
        from controllers.comic_controller import ComicController as CC

        # Reader
        default_zoom_index = self.settings.value(
            CC.SETTINGS_DEFAULT_ZOOM, 3, type=int
        )
        self.default_zoom_combo.setCurrentIndex(default_zoom_index)

        # Library
        sensitivity = self.settings.value(
            CC.SETTINGS_SENSITIVITY, 0.8, type=float
        )
        self.sensitivity_spinbox.setValue(sensitivity * 100)

    def accept(self):
        """Save settings and close the dialog."""
        from controllers.comic_controller import ComicController as CC

        # Reader
        self.settings.setValue(
            CC.SETTINGS_DEFAULT_ZOOM, self.default_zoom_combo.currentIndex()
        )

        # Library
        self.settings.setValue(
            CC.SETTINGS_SENSITIVITY, self.sensitivity_spinbox.value() / 100
        )
        super().accept()
