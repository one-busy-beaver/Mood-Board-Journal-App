"""Bounded workspace that hosts note windows (replaces the infinite canvas).

Notes are absolutely-positioned child widgets; there is no zoom/pan of a plane.
The global text scale ("resolution") is applied to every note window.

Creation gestures on empty space:
  - single click  → deselect only
  - double click  → a new note at the default size
  - click + drag  → a new note of exactly the dragged size, with a live preview
                    rectangle (tiny drags are ignored; small ones clamp to the
                    minimum note size)

**Rotated notes.** Qt cannot rotate a live QWidget, so a rotated note hides its
real widget and is painted here from a snapshot, transformed about its centre.
Hit-testing goes through `NoteWindow.contains_scene_point`, which applies the
inverse rotation — so clicks land correctly at any angle.
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

from models.note import Note
from views.note_window import NoteWindow


class Workspace(QWidget):
    # x, y, w, h in workspace coords (w/h = 0 means "use the default size")
    create_note_requested = pyqtSignal(float, float, float, float)
    background_clicked = pyqtSignal()                 # click landed on empty space

    GRID = 40
    DRAG_IGNORE = 20    # a drag shorter than this in both axes is a stray click
    MIN_W = 140         # below this (but above DRAG_IGNORE) clamps up
    MIN_H = 110

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self._windows: dict[str, NoteWindow] = {}
        self._rubber_origin: QPointF | None = None
        self._rubber_rect: QRectF | None = None
        self._drag_note: NoteWindow | None = None   # rotated note being dragged
        self._frame: "SelectionFrame | None" = None
        self.setMouseTracking(True)
        self.setStyleSheet("background: #1c1917;")

    # ── Note lifecycle ────────────────────────────────────────────────────────

    def add_note(self, note: Note) -> NoteWindow:
        nw = NoteWindow(note, self._scale, self)
        self._windows[note.id] = nw
        nw.show()
        self._sync_rotation_visibility(nw)
        return nw

    def ensure_in_bounds(self):
        """Pull any note that sits outside the visible area back inside.

        Notes are stored in absolute coords, so a journal laid out in a large
        window (or at a larger scale) can place notes past the edge of a smaller
        one. There is no pan/scroll, so an off-edge note would be unreachable.
        Only notes actually out of bounds move, and the model is updated so the
        correction survives a save."""
        if self.width() <= 0 or self.height() <= 0:
            return
        for nw in self._windows.values():
            x, y = nw.x(), nw.y()
            max_x = max(0, self.width() - nw.width())
            max_y = max(0, self.height() - nw.height())
            nx, ny = min(max(0, x), max_x), min(max(0, y), max_y)
            if (nx, ny) != (x, y):
                nw.move(nx, ny)
                nw.emit_geometry()

    def remove_note(self, note_id: str):
        nw = self._windows.pop(note_id, None)
        if nw is not None:
            nw.deleteLater()

    def window(self, note_id: str) -> NoteWindow | None:
        return self._windows.get(note_id)

    def windows(self) -> list[NoteWindow]:
        return list(self._windows.values())

    # ── Stacking ──────────────────────────────────────────────────────────────

    def clear_selection(self):
        """Drop the selection flag from every note (click on empty space)."""
        for nw in self._windows.values():
            nw.set_selected(False)

    def raise_note(self, note_id: str):
        nw = self._windows.get(note_id)
        if nw is not None:
            nw.raise_()

    def restack(self):
        """Re-apply persistent z-order (ascending z_index = bottom to top).

        The selection frame is raised last so the highlighter always sits on top
        even though the selected note itself stays at its own depth."""
        for nw in sorted(self._windows.values(), key=lambda w: w.z_index()):
            nw.raise_()
        frame = getattr(self, "_frame", None)
        if frame is not None:
            frame.raise_()

    def cancel_gestures(self):
        """Abandon an in-flight note drag or rubber-band selection."""
        if self._drag_note is not None:
            self._drag_note.end_external_drag()
            self._drag_note = None
        for nw in self._windows.values():
            nw.cancel_drag()
        self._rubber_origin = None
        self._rubber_rect = None
        self.update()

    def note_at(self, pos: QPointF) -> NoteWindow | None:
        """Topmost note under `pos`, honouring rotation. Used to route clicks
        that the selection frame let through."""
        for nw in sorted(self._windows.values(), key=lambda w: w.z_index(),
                         reverse=True):
            if nw.contains_scene_point(pos):
                return nw
        return None

    # ── Scale ─────────────────────────────────────────────────────────────────

    def apply_scale(self, scale: float):
        self._scale = scale
        for nw in self._windows.values():
            nw.apply_scale(scale)
        self.ensure_in_bounds()

    # ── Rotation ──────────────────────────────────────────────────────────────

    def refresh_rotation(self, note_id: str | None = None):
        """Show/hide real widgets depending on whether they are rotated, then
        repaint so snapshots are redrawn at the new angle."""
        targets = ([self._windows[note_id]] if note_id in self._windows
                   else self._windows.values())
        for nw in targets:
            self._sync_rotation_visibility(nw)
        self.update()

    @staticmethod
    def _sync_rotation_visibility(nw: NoteWindow):
        """A rotated note is drawn by `paintEvent` from a snapshot, so the real
        (axis-aligned) widget must not also paint itself. Unrotated notes stay
        ordinary visible widgets — no snapshot cost in the common case.

        `QWidget.grab()` works on a hidden widget as long as it has been sized,
        so hiding is enough; no opacity tricks are needed."""
        nw.setVisible(not nw.is_rotated())

    # ── Events ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        # Note windows consume their own presses, so reaching here means the
        # click landed on empty canvas — unless a rotated note (which is painted,
        # not laid out) is under the cursor.
        if e.button() == Qt.MouseButton.LeftButton:
            # Normally Qt delivers handle presses straight to the frame (it is
            # a child on top and stays interactive while attached), and the
            # frame then grabs the mouse for the rest of the gesture. This is
            # only a fallback for a press that still arrives here — e.g. a
            # synthesised event aimed at the workspace. Guard on the frame not
            # already being busy, so a press is never handled twice: doing so
            # reset the rotation's reference angle mid-drag.
            frame = getattr(self, "_frame", None)
            if frame is not None and not frame.is_busy() and frame.wants(e.position()):
                frame.mousePressEvent(e)
                e.accept()
                return
            hit = self.note_at(e.position())
            if hit is not None:
                # Only rotated notes reach here (unrotated ones get their own
                # events); drive their drag from the workspace.
                hit.activate()
                self._drag_note = hit
                hit.begin_external_drag(e.position())
                e.accept()
                return
            self.background_clicked.emit()
            self._rubber_origin = QPointF(e.position())
            self._rubber_rect = None
            e.accept()
            return
        super().mousePressEvent(e)

    def _update_frame_interactivity(self, pos: QPointF):
        """The frame paints over the whole workspace but must only *receive*
        clicks on its handles, so toggle its mouse-transparency on hover."""
        frame = getattr(self, "_frame", None)
        if frame is None:
            return
        over = frame.wants(pos)
        frame.set_interactive(over)
        if over:
            self.setCursor(frame.cursor_for(frame._hit(pos)))
        else:
            self.unsetCursor()

    def mouseMoveEvent(self, e):
        self._update_frame_interactivity(e.position())
        if getattr(self, "_drag_note", None) is not None:
            self._drag_note.drag_to(e.position())
            self.update()
            e.accept()
            return
        if self._rubber_origin is not None:
            self._rubber_rect = QRectF(self._rubber_origin,
                                       QPointF(e.position())).normalized()
            self.update()
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if getattr(self, "_drag_note", None) is not None:
            self._drag_note.end_external_drag()
            self._drag_note = None
            self.update()
            e.accept()
            return
        if self._rubber_origin is not None:
            rect = self._rubber_rect
            self._rubber_origin = None
            self._rubber_rect = None
            self.update()
            if rect is not None:
                w, h = rect.width(), rect.height()
                # Tiny drags are stray clicks: create nothing. Small-but-real
                # drags clamp up to the minimum note size.
                if w >= self.DRAG_IGNORE or h >= self.DRAG_IGNORE:
                    self.create_note_requested.emit(
                        rect.x(), rect.y(),
                        max(w, self.MIN_W * self._scale),
                        max(h, self.MIN_H * self._scale),
                    )
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        # A double-click on empty space creates a default-sized note. Any
        # in-flight rubber band from the first click is discarded.
        self._rubber_origin = None
        self._rubber_rect = None
        hit = self.note_at(e.position())
        if hit is not None:
            # The double-click landed on a note rather than empty canvas. We get
            # here when the note could not receive the event itself: it is
            # rotated (painted from a snapshot, so it has no live widget), or the
            # selection frame is over it and forwarded the event down. Either
            # way, open that note's editor — the only route into editing.
            hit.cancel_drag()          # the preceding press started a drag
            hit.expand_requested.emit(hit.note_id)
            e.accept()
            return
        pos = e.position()
        self.create_note_requested.emit(pos.x(), pos.y(), 0.0, 0.0)

    def set_selection_frame(self, frame):
        """The frame is a sibling child covering the whole workspace; it must
        follow our size and stay above every note."""
        self._frame = frame
        frame.setGeometry(self.rect())
        frame.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        frame = getattr(self, "_frame", None)
        if frame is not None:
            frame.setGeometry(self.rect())
        self.ensure_in_bounds()

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

        # Rotated notes are painted here (bottom-to-top) from snapshots, since
        # Qt cannot rotate the live widgets themselves.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for nw in sorted(self._windows.values(), key=lambda w: w.z_index()):
            if not nw.is_rotated():
                continue
            pm = nw.grab()
            if pm.isNull():
                continue
            r = QRectF(nw.geometry())
            painter.save()
            painter.translate(r.center())
            painter.rotate(nw.angle())
            painter.translate(-r.width() / 2.0, -r.height() / 2.0)
            painter.drawPixmap(QPoint(0, 0), pm)
            painter.restore()

        # Live preview of a drag-to-create rectangle.
        if self._rubber_rect is not None:
            painter.setPen(QPen(QColor("#f59e0b"), 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(245, 158, 11, 40)))
            painter.drawRect(self._rubber_rect)
