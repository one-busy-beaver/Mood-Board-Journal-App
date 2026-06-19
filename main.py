import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from controllers.board_controller import BoardController
from controllers.persistence_controller import PersistenceController
from views.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Journal")
    app.setFont(QFont("Segoe UI", 10))

    persistence = PersistenceController()
    board = persistence.load()
    board_ctrl = BoardController(board)

    window = MainWindow(board_ctrl, persistence)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
