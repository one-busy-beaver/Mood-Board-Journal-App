from PyQt6.QtCore import QObject, pyqtSignal
from models.note import Note, NoteGeometry
from models.board import Board


class BoardController(QObject):
    note_added = pyqtSignal(object)    # Note
    note_removed = pyqtSignal(str)     # note_id
    board_changed = pyqtSignal()
    z_order_changed = pyqtSignal(str, float)  # note_id, new_z

    def __init__(self, board: Board):
        super().__init__()
        self._board = board
        self._max_z = max((n.geometry.z_index for n in board.notes), default=0.0)

    @property
    def board(self) -> Board:
        return self._board

    def create_note(self, x: float, y: float) -> Note:
        note = Note(geometry=NoteGeometry(x=x, y=y, z_index=self._next_z()))
        self._board.notes.append(note)
        self.note_added.emit(note)
        self.board_changed.emit()
        return note

    def remove_note(self, note_id: str):
        self._board.notes = [n for n in self._board.notes if n.id != note_id]
        self.note_removed.emit(note_id)
        self.board_changed.emit()

    def update_geometry(self, note_id: str, x: float = None, y: float = None,
                        width: float = None, height: float = None):
        note = self._find(note_id)
        if note is None:
            return
        if x is not None:
            note.geometry.x = x
        if y is not None:
            note.geometry.y = y
        if width is not None:
            note.geometry.width = width
        if height is not None:
            note.geometry.height = height
        self.board_changed.emit()

    def bring_to_front(self, note_id: str) -> float:
        note = self._find(note_id)
        if note:
            note.geometry.z_index = self._next_z()
            self.z_order_changed.emit(note_id, note.geometry.z_index)
            return note.geometry.z_index
        return self._max_z

    def send_to_back(self, note_id: str):
        note = self._find(note_id)
        if note is None:
            return
        min_z = min((n.geometry.z_index for n in self._board.notes), default=0.0)
        note.geometry.z_index = min_z - 1
        self.z_order_changed.emit(note_id, note.geometry.z_index)
        self.board_changed.emit()

    def reorder_one_up(self, note_id: str):
        note = self._find(note_id)
        if note is None:
            return
        by_z = sorted(self._board.notes, key=lambda n: n.geometry.z_index)
        idx = next((i for i, n in enumerate(by_z) if n.id == note_id), -1)
        if idx < 0 or idx >= len(by_z) - 1:
            return
        above = by_z[idx + 1]
        note.geometry.z_index, above.geometry.z_index = above.geometry.z_index, note.geometry.z_index
        self.z_order_changed.emit(note_id, note.geometry.z_index)
        self.z_order_changed.emit(above.id, above.geometry.z_index)
        self.board_changed.emit()

    def reorder_one_down(self, note_id: str):
        note = self._find(note_id)
        if note is None:
            return
        by_z = sorted(self._board.notes, key=lambda n: n.geometry.z_index)
        idx = next((i for i, n in enumerate(by_z) if n.id == note_id), -1)
        if idx <= 0:
            return
        below = by_z[idx - 1]
        note.geometry.z_index, below.geometry.z_index = below.geometry.z_index, note.geometry.z_index
        self.z_order_changed.emit(note_id, note.geometry.z_index)
        self.z_order_changed.emit(below.id, below.geometry.z_index)
        self.board_changed.emit()

    def update_content(self, note_id: str, content: dict):
        note = self._find(note_id)
        if note:
            note.content = content
            self.board_changed.emit()

    def update_title(self, note_id: str, title: str):
        note = self._find(note_id)
        if note:
            note.title = title
            self.board_changed.emit()

    def _find(self, note_id: str) -> Note | None:
        return next((n for n in self._board.notes if n.id == note_id), None)

    def _next_z(self) -> float:
        self._max_z += 1
        return self._max_z
