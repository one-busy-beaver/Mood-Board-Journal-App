import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from controllers.library_controller import LibraryController
from controllers.settings_controller import SettingsController
from controllers.persistence_controller import PersistenceController
from views.main_window import MainWindow
from utils.shortcuts import ShortcutMap


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Journal")
    app.setFont(QFont("Segoe UI", 10))

    persistence = PersistenceController()
    library = persistence.load_library()      # migrates a legacy board.json once
    library_ctrl = LibraryController(library, persistence)
    # Global palette, shared by every journal (migrated from per-journal lists).
    settings_ctrl = SettingsController(persistence.load_settings(library), persistence)
    shortcuts = ShortcutMap()  # pass overrides or ShortcutMap.from_file() here later

    window = MainWindow(library_ctrl, settings_ctrl, persistence, shortcuts)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
