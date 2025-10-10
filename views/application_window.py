from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QMainWindow, QStackedWidget, QAction
from PyQt5.QtGui import QGuiApplication

from .library_view import LibraryView
from .chapter_view import ChapterListView
from .reader_view import ReaderView


class ApplicationWindow(QMainWindow):
    dark_mode_toggled = pyqtSignal(bool)
    settings_requested = pyqtSignal()
    closing = pyqtSignal()

    DARK_STYLE = """
        QMainWindow, QDialog { background-color: #2b2b2b; }
        QWidget { background-color: #3c3c3c; color: #dcdcdc; }
        QLabel { color: #dcdcdc; }
        QPushButton, QToolButton {
            background-color: #555555;
            color: #dcdcdc;
            border: 1px solid #666666;
            padding: 5px;
            border-radius: 4px;
        }
        QPushButton:hover, QToolButton:hover { background-color: #6a6a6a; }
        QPushButton:pressed, QToolButton:pressed { background-color: #4a4a4a; }
        QLineEdit {
            background-color: #2b2b2b;
            border: 1px solid #555555;
            padding: 4px;
            border-radius: 4px;
        }
        QComboBox {
            background-color: #555555;
            border: 1px solid #666666;
            padding: 4px;
            border-radius: 4px;
        }
        QComboBox::drop-down { border: none; }
        QScrollArea { border: none; }
        QScrollBar:vertical {
            background: #2b2b2b;
            width: 12px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #555;
            min-height: 20px;
            border-radius: 6px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
    """

    def __init__(self, controller=None) -> None:
        super().__init__()
        self.setWindowTitle("Comic Reader")
        self.controller = controller

        # Default size, will be overridden by saved geometry
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(int(screen.width() * 0.7), int(screen.height() * 0.8))
        self.center()

        self._create_actions()
        self._create_menu()

        self.library_view = LibraryView(controller=self.controller)
        self.chapter_list_view = ChapterListView(controller=self.controller)
        self.reader_view = ReaderView(controller=self.controller)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.library_view)
        self.stack.addWidget(self.chapter_list_view)
        self.stack.addWidget(self.reader_view)

        self.setCentralWidget(self.stack)

    def _create_actions(self):
        self.settings_action = QAction("&Settings...", self)
        self.settings_action.triggered.connect(self.settings_requested)
        self.toggle_dark_mode_action = QAction("Toggle &Dark Mode", self, checkable=True)
        self.toggle_dark_mode_action.triggered.connect(
            lambda: self.dark_mode_toggled.emit(self.toggle_dark_mode_action.isChecked())
        )

    def _create_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.settings_action)
        view_menu = menu_bar.addMenu("&View")
        view_menu.addAction(self.toggle_dark_mode_action)


    def center(self):
        qr = self.frameGeometry()
        cp = QGuiApplication.primaryScreen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def toggle_dark_mode(self, is_dark: bool):
        self.setStyleSheet(self.DARK_STYLE if is_dark else "")
        self.toggle_dark_mode_action.setChecked(is_dark)
        # Propagate style change to children that might need it
        self.library_view.set_dark_mode(is_dark)
        self.chapter_list_view.set_dark_mode(is_dark)
        self.reader_view.set_dark_mode(is_dark)

    def closeEvent(self, event):
        self.closing.emit()
        super().closeEvent(event)

    # --- Convenience Helpers ---
    def show_library(self) -> None:
        self.stack.setCurrentWidget(self.library_view)

    def show_chapters(self) -> None:
        self.stack.setCurrentWidget(self.chapter_list_view)

    def show_reader(self) -> None:
        self.stack.setCurrentWidget(self.reader_view)
