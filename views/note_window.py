"""A note rendered as a real sticky note — no title bar, no buttons.

Interaction model:
  - hover shows a move cursor: the whole note is a drag handle
  - drag from anywhere on the body to move it
  - single click selects (does NOT change stacking — z_index owns that)
  - DOUBLE-CLICK opens the zoomed editor overlay; that is the ONLY way to edit
    text. The body is display-only here (read-only, no caret, no focus).

Resizing and rotation are NOT handled here — they belong to `SelectionFrame`,
which floats above every note so its handles are never buried, and are only
offered while the note is selected. That is why this widget shows no resize
cursor on its edges: an unselected note is not resizable.

**Rotation.** Qt cannot rotate a live QWidget (there is no `setRotation`), so a
rotated note is painted by `Workspace` from a snapshot of this widget while the
real widget stays unrotated and hidden. Nothing is lost: notes are read-only
display cards, and editing happens in the unrotated zoom view.
`contains_scene_point()` is the matching rotation-aware hit-test.
"""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QGraphicsDropShadowEffect, QWidget,
)
from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QCursor

from models.note import Note
from views.templates.plain_text import PlainTextTemplate
from utils.contrast import ink

_BODY_STYLE = """
    QTextEdit {{
        background: transparent;
        border: none;
        color: {ink};
        selection-background-color: #fde68a;
        padding: 2px;
    }}
    QScrollBar:vertical {{ width: 4px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: #d6d3d1; border-radius: 2px; }}
"""


class NoteWindow(QFrame):
    # Signals → consumed by MainWindow / BoardController.
    # `content_changed` is kept for interface compatibility but is no longer
    # emitted from here: the card is read-only, so edits come from the overlay.
    removed = pyqtSignal(str)
    expand_requested = pyqtSignal(str)
    geometry_changed = pyqtSignal(str, float, float, float, float)
    content_changed = pyqtSignal(str, dict)
    bring_to_front_requested = pyqtSignal(str)
    moved = pyqtSignal(str)          # live during a drag, so chrome can follow

    MIN_W = 140
    MIN_H = 110
    PAD = 12              # inner padding around the body text (base units)

    def __init__(self, note: Note, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._note = note
        self._scale = scale
        self._selected = False

        self._dragging = False
        self._grab_offset = QPoint()

        self.setObjectName("noteWindow")
        self.setMouseTracking(True)
        # A sticky note is a draggable object; say so on hover. Resize cursors
        # appear only on the selection frame's handles.
        self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(18)
        self._shadow.setOffset(0, 3)
        self._shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(self._shadow)

        self._root = QVBoxLayout(self)
        self._root.setSpacing(0)

        # Display-only body. Transparent to mouse events so clicks, drags and
        # double-clicks all land on the note itself — the sticky behaves as one
        # solid object rather than a text box in a frame.
        self._body = PlainTextTemplate(note.content, compact=True,
                                       text_color=ink(note.color))
        self._body.setReadOnly(True)
        self._body.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._body.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._body.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._root.addWidget(self._body, 1)

        self.apply_scale(scale)
        self._apply_style()
        self._retint_body()

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def note(self) -> Note:
        return self._note

    @property
    def note_id(self) -> str:
        return self._note.id

    def z_index(self) -> float:
        return self._note.geometry.z_index

    def angle(self) -> float:
        return self._note.geometry.rotation

    def is_rotated(self) -> bool:
        return abs(self._note.geometry.rotation % 360.0) > 1e-6

    def activate(self):
        """Mark this note active. Deliberately does NOT raise it: stacking is
        owned by `z_index` and only the reorder shortcuts change it."""
        self.bring_to_front_requested.emit(self._note.id)

    def set_selected(self, selected: bool):
        """Selection chrome lives in `SelectionFrame`, so the note only records
        the flag — the frame is the single visual indicator."""
        self._selected = selected

    def apply_scale(self, scale: float):
        """Global UI zoom: re-lay-out the note box (base geometry × scale) and
        its padding. Body font is intentionally NOT scaled here."""
        self._scale = scale
        pad = max(6, round(self.PAD * scale))
        self._root.setContentsMargins(pad, pad, pad, pad)
        self._relayout()

    def _relayout(self):
        g = self._note.geometry
        s = self._scale
        self.setGeometry(round(g.x * s), round(g.y * s),
                         round(g.width * s), round(g.height * s))
        self.apply_font()

    def apply_font(self):
        """Body font = the note's own font_size (per-note). Independent of the
        global 'resolution' scale."""
        self._body.setFont(QFont("Georgia", max(6, self._note.font_size)))

    def refresh_color(self):
        self._apply_style()
        # Body text has to follow the note's colour, or a dark note swallows it.
        self._retint_body()

    def _retint_body(self):
        self._body.setStyleSheet(_BODY_STYLE.format(ink=ink(self._note.color)))

    def sync_from_model(self):
        """Refresh the displayed text after the overlay commits an edit."""
        self._body.setPlainText(self._note.content.get("body", ""))

    # ── Geometry in workspace coordinates ────────────────────────────────────

    def scene_rect(self) -> QRectF:
        """The note's UNROTATED box in workspace (screen) coordinates."""
        g = self._note.geometry
        s = self._scale
        return QRectF(g.x * s, g.y * s, g.width * s, g.height * s)

    def contains_scene_point(self, p: QPointF) -> bool:
        """Rotation-aware hit-test: map the point back into the note's own
        unrotated space, then test the plain rect."""
        from views.widgets.selection_frame import rotate
        r = QRectF(self.geometry())           # live position (may be mid-drag)
        local = rotate(QPointF(p), r.center(), -self.angle())
        return r.contains(local)

    def move_clamped(self, x: int, y: int):
        ws = self.parentWidget()
        if ws is not None:
            # Keep a grabbable strip on screen at all times.
            x = max(-(self.width() - 80), min(x, ws.width() - 80))
            y = max(0, min(y, ws.height() - 40))
        self.move(int(x), int(y))

    def emit_geometry(self):
        # The widget lives in screen pixels; the model stores base (unscaled)
        # coords, so divide back out the current scale.
        g = self.geometry()
        s = self._scale or 1.0
        self.geometry_changed.emit(
            self._note.id, g.x() / s, g.y() / s, g.width() / s, g.height() / s,
        )

    def begin_external_drag(self, scene_pos: QPointF):
        """Start a drag driven by the Workspace.

        A rotated note is painted rather than laid out, so it gets no mouse
        events of its own; the workspace hit-tests it and hands the drag over.

        Deliberately NO grabMouse(): the Workspace already received the press
        and therefore holds Qt's implicit grab, so it gets the whole gesture and
        forwards it here. An explicit grab would be taken by a HIDDEN widget
        (a rotated note hides its real widget and is painted from a snapshot),
        and a hidden widget never receives the release that would free it —
        freezing every click in the application.
        """
        self._grab_offset = QPoint(int(scene_pos.x()) - self.x(),
                                   int(scene_pos.y()) - self.y())
        self._dragging = True

    def drag_to(self, scene_pos: QPointF):
        if not self._dragging:
            return
        self.move_clamped(int(scene_pos.x()) - self._grab_offset.x(),
                          int(scene_pos.y()) - self._grab_offset.y())
        self.moved.emit(self._note.id)

    def end_external_drag(self):
        if self._dragging:
            self._dragging = False
            if QWidget.mouseGrabber() is self:
                self.releaseMouse()
            self.emit_geometry()

    def cancel_drag(self):
        """Drop an in-flight drag without committing, releasing any grab."""
        self._dragging = False
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()

    def set_scene_rect(self, x: float, y: float, w: float, h: float):
        """Apply a screen-space box (used by SelectionFrame while resizing)."""
        self.setGeometry(round(x), round(y), round(w), round(h))

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet(f"""
            QFrame#noteWindow {{
                background: {self._note.color};
                border: 1px solid rgba(0, 0, 0, 0.18);
                border-radius: 4px;
            }}
        """)

    # ── Mouse: drag the body; double-click to edit ───────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.activate()
            ws = self.parentWidget()
            self._grab_offset = (
                ws.mapFromGlobal(e.globalPosition().toPoint()) - self.pos()
            )
            self._dragging = True
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging:
            ws = self.parentWidget()
            target = ws.mapFromGlobal(e.globalPosition().toPoint()) - self._grab_offset
            self.move_clamped(target.x(), target.y())
            self.moved.emit(self._note.id)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self._dragging = False
            self.emit_geometry()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        """The only route into editing: open the zoomed overlay."""
        if e.button() == Qt.MouseButton.LeftButton:
            # A double-click follows a press that started a drag; cancel it so the
            # note doesn't jitter when the overlay opens.
            self._dragging = False
            self.expand_requested.emit(self._note.id)
            e.accept()
            return
        super().mouseDoubleClickEvent(e)
