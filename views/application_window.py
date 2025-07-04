from PyQt5.QtWidgets import QMainWindow, QStackedWidget, QApplication
from PyQt5.QtGui import QGuiApplication

from PyQt5.QtWidgets import QMainWindow, QStackedWidget, QApplication
from PyQt5.QtGui import QGuiApplication

from views import LibraryView, ChapterListView, ReaderView


class ApplicationWindow(QMainWindow):
    def __init__(self, controller=None) -> None:
        super().__init__()
        self.setWindowTitle("Comic Reader")

        # Get screen size using QScreen
        screen = QGuiApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()

        # Resize window to 80% of screen size
        self.resize(int(screen_width * 0.8), int(screen_height * 0.8))

        self.library_view = LibraryView(controller=controller)
        self.chapter_list_view = ChapterListView()
        self.reader_view = ReaderView()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.library_view)
        self.stack.addWidget(self.chapter_list_view)
        self.stack.addWidget(self.reader_view)

        self.setCentralWidget(self.stack)



    # Convenience helpers ----------------------------------------------
    def show_library(self) -> None:
        self.stack.setCurrentWidget(self.library_view)

    def show_chapters(self) -> None:
        self.stack.setCurrentWidget(self.chapter_list_view)

    def show_reader(self) -> None:
        self.stack.setCurrentWidget(self.reader_view)
