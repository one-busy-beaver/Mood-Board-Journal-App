"""A note rendered as a draggable, resizable in-app window (QFrame child of the
Workspace). Behaves like an OS window: drag by the title bar, resize from any
edge/corner, and raise on interaction. Emits the same signals the old NoteItem
did, so MainWindow wiring is unchanged."""

from PyQt6.QtWidgets import (
    QFrame, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QPoint, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QCursor

from models.note import Note
from views.templates.plain_text import PlainTextTemplate


_CURSOR_MAP = {
    "N":  Qt.CursorShape.SizeVerCursor,
    "S":  Qt.CursorShape.SizeVerCursor,
    "E":  Qt.CursorShape.SizeHorCursor,
    "W":  Qt.CursorShape.SizeHorCursor,
    "NE": Qt.CursorShape.SizeBDiagCursor,
    "SW": Qt.CursorShape.SizeBDiagCursor,
    "NW": Qt.CursorShape.SizeFDiagCursor,
    "SE": Qt.CursorShape.SizeFDiagCursor,
    "":   Qt.CursorShape.ArrowCursor,
}


class _TitleBar(QWidget):
    """Drag handle + expand/close buttons. Moves its owning NoteWindow."""

    BASE_H = 30
    BASE_PT = 9
    BASE_BTN = 18

    def __init__(self, win: "NoteWindow"):
        super().__init__(win)
        self._win = win
        self._dragging = False
        self._grab_offset = QPoint()
        self.setObjectName("titleBar")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 6, 0)
        lay.setSpacing(4)

        self._title = QLabel(win.note.title)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._title.setStyleSheet("color: #44403c; background: transparent;")
        lay.addWidget(self._title)
        lay.addStretch()

        self._expand = self._make_btn("⤢", "Expand  (double-click body)")
        self._expand.clicked.connect(
            lambda: win.expand_requested.emit(win.note.id)
        )
        lay.addWidget(self._expand)

        self._close = self._make_btn("✕", "Delete note")
        self._close.clicked.connect(lambda: win.removed.emit(win.note.id))
        lay.addWidget(self._close)

    def _make_btn(self, glyph: str, tip: str) -> QPushButton:
        b = QPushButton(glyph)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet("""
            QPushButton { color: #78716c; background: transparent; border: none;
                          padding: 0; font-weight: bold; }
            QPushButton:hover { color: #1c1917; }
        """)
        return b

    def set_title(self, text: str):
        self._title.setText(text)

    def apply_scale(self, scale: float):
        self.setFixedHeight(round(self.BASE_H * scale))
        self._title.setFont(QFont("Segoe UI", max(6, round(self.BASE_PT * scale)),
                                  QFont.Weight.Medium))
        btn = max(14, round(self.BASE_BTN * scale))
        for b in (self._expand, self._close):
            b.setFixedSize(btn, btn)
            f = b.font(); f.setPointSize(max(8, round(11 * scale))); b.setFont(f)

    # ── Drag ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._win.activate()
            ws = self._win.parentWidget()
            self._grab_offset = (
                ws.mapFromGlobal(e.globalPosition().toPoint()) - self._win.pos()
            )
            self._dragging = True
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging:
            ws = self._win.parentWidget()
            target = ws.mapFromGlobal(e.globalPosition().toPoint()) - self._grab_offset
            self._win.move_clamped(target.x(), target.y())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self._dragging = False
            self._win.emit_geometry()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        self._win.expand_requested.emit(self._win.note.id)
        e.accept()


class NoteWindow(QFrame):
    # Signals → consumed by MainWindow / BoardController (same as old NoteItem)
    removed = pyqtSignal(str)
    expand_requested = pyqtSignal(str)
    geometry_changed = pyqtSignal(str, float, float, float, float)
    content_changed = pyqtSignal(str, dict)
    bring_to_front_requested = pyqtSignal(str)

    MIN_W = 140
    MIN_H = 110
    RESIZE_MARGIN = 7

    def __init__(self, note: Note, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._note = note
        self._scale = scale

        self._resizing = False
        self._resize_dir = ""
        self._resize_start = QPoint()
        self._start_geom = (0, 0, 0, 0)

        self.setObjectName("noteWindow")
        self.setMouseTracking(True)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(shadow)

        m = self.RESIZE_MARGIN
        root = QVBoxLayout(self)
        root.setContentsMargins(m, m, m, m)
        root.setSpacing(0)

        self._titlebar = _TitleBar(self)
        root.addWidget(self._titlebar)

        self._editor = PlainTextTemplate(note.content, compact=True)
        self._editor.setMouseTracking(True)
        self._editor.installEventFilter(self)
        root.addWidget(self._editor, 1)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_content)
        self._editor.textChanged.connect(lambda: self._save_timer.start(400))

        self.apply_scale(scale)  # lays out geometry (base × scale) + chrome + font
        self._apply_style()

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def note(self) -> Note:
        return self._note

    @property
    def note_id(self) -> str:
        return self._note.id

    def z_index(self) -> float:
        return self._note.geometry.z_index

    def activate(self):
        """Raise this window and mark it active (visual raise only — persistent
        z changes go through explicit reorder shortcuts)."""
        self.raise_()
        self.bring_to_front_requested.emit(self._note.id)

    def apply_scale(self, scale: float):
        """Global UI zoom: re-lay-out the note box (base geometry × scale) and its
        chrome (title bar). Body font is intentionally NOT scaled here."""
        self._scale = scale
        self._relayout()
        self._titlebar.apply_scale(scale)
        self.apply_font()

    def _relayout(self):
        g = self._note.geometry
        s = self._scale
        self.setGeometry(round(g.x * s), round(g.y * s),
                         round(g.width * s), round(g.height * s))

    def apply_font(self):
        """Body font = the note's own font_size (per-note). Independent of the
        global 'resolution' scale."""
        self._editor.setFont(QFont("Georgia", max(6, self._note.font_size)))

    def refresh_color(self):
        self._apply_style()

    def sync_from_model(self):
        """Refresh editor text + title after an external change (overlay commit)."""
        self._editor.blockSignals(True)
        self._editor.setPlainText(self._note.content.get("body", ""))
        self._editor.blockSignals(False)
        self._titlebar.set_title(self._note.title)

    def move_clamped(self, x: int, y: int):
        ws = self.parentWidget()
        if ws is not None:
            # Keep the title bar reachable: don't let it leave the top or slide
            # fully off the sides.
            x = max(-(self.width() - 80), min(x, ws.width() - 80))
            y = max(0, min(y, ws.height() - self._titlebar.height()))
        self.move(int(x), int(y))

    def emit_geometry(self):
        # The widget lives in screen pixels; the model stores base (unscaled)
        # coords, so divide back out the current scale.
        g = self.geometry()
        s = self._scale or 1.0
        self.geometry_changed.emit(
            self._note.id, g.x() / s, g.y() / s, g.width() / s, g.height() / s,
        )

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_style(self):
        base = QColor(self._note.color)
        tint = QColor(int(base.red() * 0.93),
                      int(base.green() * 0.93),
                      int(base.blue() * 0.93)).name()
        self.setStyleSheet(f"""
            QFrame#noteWindow {{
                background: {self._note.color};
                border: 1px solid rgba(0, 0, 0, 0.18);
                border-radius: 8px;
            }}
            QWidget#titleBar {{
                background: {tint};
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                border-bottom: 1px solid rgba(0, 0, 0, 0.12);
            }}
        """)

    # ── Resize (edge/corner drag on the frame margin) ─────────────────────────

    def _resize_dir_at(self, pos) -> str:
        m = self.RESIZE_MARGIN
        w, h = self.width(), self.height()
        d = ""
        if pos.y() <= m:
            d += "N"
        elif pos.y() >= h - m:
            d += "S"
        if pos.x() <= m:
            d += "W"
        elif pos.x() >= w - m:
            d += "E"
        return d

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            d = self._resize_dir_at(e.position().toPoint())
            if d:
                self.activate()
                self._resizing = True
                self._resize_dir = d
                self._resize_start = e.globalPosition().toPoint()
                g = self.geometry()
                self._start_geom = (g.x(), g.y(), g.width(), g.height())
                e.accept()
                return
            # A bare click on the card (not an edge) still raises it.
            self.activate()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._resizing:
            self._do_resize(e.globalPosition().toPoint())
            e.accept()
            return
        self.setCursor(QCursor(_CURSOR_MAP[self._resize_dir_at(e.position().toPoint())]))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._resizing:
            self._resizing = False
            self.emit_geometry()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def _do_resize(self, global_pos):
        dx = global_pos.x() - self._resize_start.x()
        dy = global_pos.y() - self._resize_start.y()
        x0, y0, w0, h0 = self._start_geom
        nx, ny, nw, nh = x0, y0, w0, h0
        d = self._resize_dir
        # Minimums are in base units; scale them to the current screen size.
        min_w = self.MIN_W * self._scale
        min_h = self.MIN_H * self._scale
        if "E" in d:
            nw = max(min_w, w0 + dx)
        if "S" in d:
            nh = max(min_h, h0 + dy)
        if "W" in d:
            nw = max(min_w, w0 - dx)
            nx = x0 + (w0 - nw)
        if "N" in d:
            nh = max(min_h, h0 - dy)
            ny = y0 + (h0 - nh)
        self.setGeometry(round(nx), round(ny), round(nw), round(nh))

    # ── Focus / content ─────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self._editor and event.type() == QEvent.Type.FocusIn:
            self.activate()
        return super().eventFilter(obj, event)

    def _flush_content(self):
        self.content_changed.emit(self._note.id, self._editor.dump())
