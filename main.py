import sys
from PyQt5.QtWidgets import QApplication
from controllers.comic_controller import ComicController


def main() -> None:
    """
    Initializes and launches the comic reader application.
    """
    app = QApplication(sys.argv)

    # The controller builds the UI and starts the application logic
    try:
        controller = ComicController()
    except SystemExit as e:
        print(f"Application exited during startup: {e}")
        sys.exit(0)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        # In a real app, you might show a QMessageBox here
        # from PyQt5.QtWidgets import QMessageBox
        # QMessageBox.critical(None, "Fatal Error", f"An unexpected error occurred:\n{e}")
        sys.exit(1)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
