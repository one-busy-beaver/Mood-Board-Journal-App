import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from controllers.board_controller import BoardController
from controllers.persistence_controller import PersistenceController
from views.main_window import MainWindow
from utils.shortcuts import ShortcutMap


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Journal")
    app.setFont(QFont("Segoe UI", 10))

    persistence = PersistenceController()
    board = persistence.load()
    board_ctrl = BoardController(board)
    shortcuts = ShortcutMap()  # pass overrides or ShortcutMap.from_file() here later

    window = MainWindow(board_ctrl, persistence, shortcuts)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
