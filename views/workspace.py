"""Bounded workspace that hosts note windows (replaces the infinite canvas).

Notes are absolutely-positioned child widgets; there is no zoom/pan of a plane.
The global text scale ("resolution") is applied to every note window.
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen

from models.note import Note
from views.note_window import NoteWindow


class Workspace(QWidget):
    create_note_requested = pyqtSignal(float, float)  # x, y in workspace coords

    GRID = 40

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._windows: dict[str, NoteWindow] = {}
        self.setMouseTracking(True)
        self.setStyleSheet("background: #1c1917;")

    # ── Note lifecycle ────────────────────────────────────────────────────────

    def add_note(self, note: Note) -> NoteWindow:
        nw = NoteWindow(note, self._scale, self)
        self._windows[note.id] = nw
        nw.show()
        return nw

    def remove_note(self, note_id: str):
        nw = self._windows.pop(note_id, None)
        if nw is not None:
            nw.deleteLater()

    def window(self, note_id: str) -> NoteWindow | None:
        return self._windows.get(note_id)

    # ── Stacking ──────────────────────────────────────────────────────────────

    def raise_note(self, note_id: str):
        nw = self._windows.get(note_id)
        if nw is not None:
            nw.raise_()

    def restack(self):
        """Re-apply persistent z-order (ascending z_index = bottom to top)."""
        for nw in sorted(self._windows.values(), key=lambda w: w.z_index()):
            nw.raise_()

    # ── Scale ─────────────────────────────────────────────────────────────────

    def apply_scale(self, scale: float):
        self._scale = scale
        for nw in self._windows.values():
            nw.apply_scale(scale)

    # ── Events ────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, e):
        # Only fires when the double-click misses every note window (children
        # consume their own events), so this always lands on empty space.
        pos = e.position()
        self.create_note_requested.emit(pos.x(), pos.y())

    def drawBackgroundGrid(self, painter: QPainter):
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1.5))
        g = self.GRID
        for x in range(0, self.width(), g):
            for y in range(0, self.height(), g):
                painter.drawPoint(x, y)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1c1917"))
        self.drawBackgroundGrid(painter)
