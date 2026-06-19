from PyQt6.QtCore import QObject
from controllers.board_controller import BoardController


class NoteController(QObject):
    def __init__(self, note_id: str, board_ctrl: BoardController):
        super().__init__()
        self._id = note_id
        self._board_ctrl = board_ctrl

    def save_content(self, content: dict):
        self._board_ctrl.update_content(self._id, content)

    def save_title(self, title: str):
        self._board_ctrl.update_title(self._id, title)
