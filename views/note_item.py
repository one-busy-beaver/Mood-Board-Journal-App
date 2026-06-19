from PyQt6.QtWidgets import (
    QGraphicsObject, QGraphicsRectItem, QGraphicsProxyWidget,
    QGraphicsItem,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QFont, QCursor,
)
from models.note import Note
from views.templates.plain_text import PlainTextTemplate


# ── Resize handle ────────────────────────────────────────────────────────────

_CURSOR_MAP = {
    "N":  Qt.CursorShape.SizeVerCursor,
    "S":  Qt.CursorShape.SizeVerCursor,
    "E":  Qt.CursorShape.SizeHorCursor,
    "W":  Qt.CursorShape.SizeHorCursor,
    "NE": Qt.CursorShape.SizeBDiagCursor,
    "SW": Qt.CursorShape.SizeBDiagCursor,
    "NW": Qt.CursorShape.SizeFDiagCursor,
    "SE": Qt.CursorShape.SizeFDiagCursor,
}


class ResizeHandle(QGraphicsRectItem):
    SIZE = 8

    def __init__(self, direction: str, note_item: "NoteItem"):
        super().__init__()
        self._dir = direction
        self._note_item = note_item
        s = self.SIZE
        self.setRect(-s / 2, -s / 2, s, s)
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#60a5fa"), 1.5))
        self.setZValue(50)
        self.setAcceptHoverEvents(True)
        self.setCursor(QCursor(_CURSOR_MAP[direction]))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresParentOpacity)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._note_item.start_resize(self._dir, e.scenePos())
            e.accept()

    def mouseMoveEvent(self, e):
        self._note_item.do_resize(e.scenePos())
        e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._note_item.end_resize()
            e.accept()


# ── Note card ────────────────────────────────────────────────────────────────

class NoteItem(QGraphicsObject):
    TITLE_H = 30
    CORNER_R = 8
    MIN_W = 120
    MIN_H = 90
    BTN_SIZE = 14
    BTN_PAD = 6

    # Signals → consumed by MainWindow / BoardController
    removed = pyqtSignal(str)
    expand_requested = pyqtSignal(str)
    color_change_requested = pyqtSignal(str)
    geometry_changed = pyqtSignal(str, float, float, float, float)
    content_changed = pyqtSignal(str, dict)
    bring_to_front_requested = pyqtSignal(str)

    def __init__(self, note: Note, parent=None):
        super().__init__(parent)
        self._note = note
        self._w = note.geometry.width
        self._h = note.geometry.height

        # Move state
        self._moving = False
        self._move_offset = QPointF()
        self._drag_z = 0.0  # z saved before drag so it can be restored after

        # Resize state
        self._resizing = False
        self._resize_dir = ""
        self._resize_start_scene = QPointF()
        self._resize_start_rect = QRectF()

        # Debounced content save
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_content)

        self.setPos(note.geometry.x, note.geometry.y)
        self.setZValue(note.geometry.z_index)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        self._setup_handles()
        self._setup_editor()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def note_id(self) -> str:
        return self._note.id

    def sync_from_model(self):
        """Refresh editor text after external content change (e.g. popup save)."""
        self._template.blockSignals(True)
        self._template.setPlainText(self._note.content.get("body", ""))
        self._template.blockSignals(False)
        self.update()

    # ── Resize protocol (called by ResizeHandle) ──────────────────────────────

    def start_resize(self, direction: str, scene_pos: QPointF):
        self._resizing = True
        self._resize_dir = direction
        self._resize_start_scene = scene_pos
        p = self.pos()
        self._resize_start_rect = QRectF(p.x(), p.y(), self._w, self._h)

    def do_resize(self, scene_pos: QPointF):
        if not self._resizing:
            return
        dx = scene_pos.x() - self._resize_start_scene.x()
        dy = scene_pos.y() - self._resize_start_scene.y()
        r = self._resize_start_rect
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        d = self._resize_dir

        if "E" in d:
            w = max(self.MIN_W, r.width() + dx)
        if "S" in d:
            h = max(self.MIN_H, r.height() + dy)
        if "W" in d:
            new_w = max(self.MIN_W, r.width() - dx)
            x = r.x() + r.width() - new_w
            w = new_w
        if "N" in d:
            new_h = max(self.MIN_H, r.height() - dy)
            y = r.y() + r.height() - new_h
            h = new_h

        self.prepareGeometryChange()
        self.setPos(x, y)
        self._w = w
        self._h = h
        self._update_layout()

    def end_resize(self):
        self._resizing = False
        p = self.pos()
        self.geometry_changed.emit(self._note.id, p.x(), p.y(), self._w, self._h)

    # ── QGraphicsItem overrides ───────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        pad = ResizeHandle.SIZE
        return QRectF(-pad, -pad, self._w + pad * 2, self._h + pad * 2)

    def paint(self, painter: QPainter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.CORNER_R
        rect = QRectF(0, 0, self._w, self._h)

        # Shadow
        shadow = rect.translated(3, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 45))
        painter.drawRoundedRect(shadow, r, r)

        # Clip all card drawing to rounded shape
        card_path = QPainterPath()
        card_path.addRoundedRect(rect, r, r)
        painter.setClipPath(card_path)

        # Card body
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._note.color))
        painter.drawRect(rect)

        # Title bar tint
        painter.setBrush(QColor(0, 0, 0, 18))
        painter.drawRect(QRectF(0, 0, self._w, self.TITLE_H))

        # Title / body divider
        painter.setPen(QPen(QColor(0, 0, 0, 25), 1))
        painter.drawLine(QPointF(0, self.TITLE_H), QPointF(self._w, self.TITLE_H))

        painter.setClipping(False)

        # Selection / border ring
        if self.isSelected():
            painter.setPen(QPen(QColor("#3b82f6"), 2))
        else:
            painter.setPen(QPen(QColor(0, 0, 0, 35), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)

        # Title text
        painter.setPen(QColor("#44403c"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        text_rect = QRectF(8, 0, self._w - self._buttons_width() - 8, self.TITLE_H)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, self._note.title)

        # Buttons
        self._paint_buttons(painter)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            for h in self._handles.values():
                h.setVisible(bool(value))
        return super().itemChange(change, value)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.bring_to_front_requested.emit(self._note.id)

            pos = e.pos()
            if self._close_rect().contains(pos):
                self.removed.emit(self._note.id)
                e.accept()
                return
            if self._expand_rect().contains(pos):
                self.expand_requested.emit(self._note.id)
                e.accept()
                return
            if self._color_rect().contains(pos):
                self.color_change_requested.emit(self._note.id)
                e.accept()
                return
            if pos.y() <= self.TITLE_H:
                self._moving = True
                self._move_offset = e.scenePos() - self.scenePos()
                self._drag_z = self.zValue()
                self.setZValue(self._drag_z + 10000)  # float above everything while dragging
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._moving:
            self.setPos(e.scenePos() - self._move_offset)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._moving:
            self._moving = False
            self.setZValue(self._drag_z)  # restore z — drag does not affect stacking order
            p = self.pos()
            self.geometry_changed.emit(self._note.id, p.x(), p.y(), self._w, self._h)
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.pos().y() > self.TITLE_H:
            self.expand_requested.emit(self._note.id)
            e.accept()
            return
        super().mouseDoubleClickEvent(e)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _setup_editor(self):
        self._template = PlainTextTemplate(self._note.content, compact=True)
        self._template.textChanged.connect(lambda: self._save_timer.start(400))
        self._proxy = QGraphicsProxyWidget(self)
        self._proxy.setWidget(self._template)
        self._proxy.setZValue(1)
        self._update_layout()

    def _setup_handles(self):
        self._handles: dict[str, ResizeHandle] = {}
        for d in ("N", "S", "E", "W", "NE", "NW", "SE", "SW"):
            h = ResizeHandle(d, self)
            h.setParentItem(self)
            h.setVisible(False)
            self._handles[d] = h
        self._place_handles()

    def _update_layout(self):
        pad = 4
        self._proxy.setPos(pad, self.TITLE_H + pad)
        self._proxy.resize(self._w - pad * 2, self._h - self.TITLE_H - pad * 2)
        self._place_handles()
        self.update()

    def _place_handles(self):
        w, h = self._w, self._h
        positions = {
            "N":  QPointF(w / 2, 0),
            "S":  QPointF(w / 2, h),
            "E":  QPointF(w, h / 2),
            "W":  QPointF(0, h / 2),
            "NE": QPointF(w, 0),
            "NW": QPointF(0, 0),
            "SE": QPointF(w, h),
            "SW": QPointF(0, h),
        }
        for d, pos in positions.items():
            self._handles[d].setPos(pos)

    def _buttons_width(self) -> float:
        return self.BTN_SIZE * 3 + self.BTN_PAD * 5

    def _color_rect(self) -> QRectF:
        bw = self.BTN_SIZE
        bp = self.BTN_PAD
        x = self._w - bw * 3 - bp * 5
        y = (self.TITLE_H - bw) / 2
        return QRectF(x, y, bw, bw)

    def _expand_rect(self) -> QRectF:
        bw = self.BTN_SIZE
        bp = self.BTN_PAD
        x = self._w - bw * 2 - bp * 3
        y = (self.TITLE_H - bw) / 2
        return QRectF(x, y, bw, bw)

    def _close_rect(self) -> QRectF:
        bw = self.BTN_SIZE
        bp = self.BTN_PAD
        x = self._w - bw - bp
        y = (self.TITLE_H - bw) / 2
        return QRectF(x, y, bw, bw)

    def _paint_buttons(self, painter: QPainter):
        er = self._expand_rect()
        cr = self._close_rect()
        clr = self._color_rect()

        # Color swatch: filled circle in note's current color with a subtle ring
        painter.setPen(QPen(QColor(0, 0, 0, 40), 1))
        painter.setBrush(QBrush(QColor(self._note.color)))
        painter.drawEllipse(clr.adjusted(1, 1, -1, -1))

        painter.setPen(QPen(QColor("#a8a29e"), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Expand icon
        painter.drawRoundedRect(er, 2, 2)
        cx, cy = er.center().x(), er.center().y()
        o = 3
        painter.drawLine(int(cx - o), int(cy + o), int(cx + o), int(cy - o))

        # Close icon: ×
        inset = 3.5
        painter.drawLine(
            int(cr.x() + inset), int(cr.y() + inset),
            int(cr.right() - inset), int(cr.bottom() - inset),
        )
        painter.drawLine(
            int(cr.right() - inset), int(cr.y() + inset),
            int(cr.x() + inset), int(cr.bottom() - inset),
        )

    def _flush_content(self):
        self.content_changed.emit(self._note.id, self._template.dump())
