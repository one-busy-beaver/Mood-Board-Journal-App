"""Selection frame: the blue outline, resize handles and rotation handle drawn
around the active note.

Why this is a separate widget rather than painting inside `NoteWindow`:
the note itself must stay at its own stacking depth (clicking a note does NOT
raise it), but its selection chrome has to be visible even when other notes
overlap it. So the frame is a transparent sibling covering the whole workspace,
kept at the very top of the stack — the note stays low, the highlighter is on top.

**Rotation maths.** A note is an axis-aligned rect in its own *local* space,
rotated by `angle` degrees clockwise about its centre. Everything here converts
between the two spaces with one pair of inverse transforms:

    to_scene(p_local)  = centre + R(+angle) · (p_local − centre)
    to_local(p_scene)  = centre + R(−angle) · (p_scene − centre)

Hit-testing maps the mouse into local space and compares against the plain
rect, so handles keep working at any angle.
"""

import math

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QEvent, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QCursor, QPolygonF

ACCENT = QColor("#3b82f6")
HANDLE_FILL = QColor("#ffffff")

# Handle order is fixed so hit-testing and painting stay in step.
CORNERS = ("NW", "NE", "SE", "SW")
EDGES = ("N", "E", "S", "W")

# Cursor per handle, for an UNROTATED note. Rotation shifts these (a "N" handle
# on a note turned 90° should read as an E/W resize), handled in cursor_for().
_BASE_ANGLE = {"E": 0, "NE": 45, "N": 90, "NW": 135,
               "W": 180, "SW": 225, "S": 270, "SE": 315}
_CURSOR_BY_OCTANT = [
    Qt.CursorShape.SizeHorCursor,   # 0   (E/W)
    Qt.CursorShape.SizeBDiagCursor, # 45  (NE/SW)
    Qt.CursorShape.SizeVerCursor,   # 90  (N/S)
    Qt.CursorShape.SizeFDiagCursor, # 135 (NW/SE)
]


def rotate(p: QPointF, centre: QPointF, degrees: float) -> QPointF:
    """Rotate `p` about `centre` by `degrees` clockwise (screen coords, y down)."""
    a = math.radians(degrees)
    ca, sa = math.cos(a), math.sin(a)
    dx, dy = p.x() - centre.x(), p.y() - centre.y()
    return QPointF(centre.x() + dx * ca - dy * sa,
                   centre.y() + dx * sa + dy * ca)


class SelectionFrame(QWidget):
    """Chrome for one selected note. Transparent to mouse events except on its
    handles, so clicks pass through to the notes underneath."""

    # note_id, x, y, w, h  (screen px, unrotated local box)
    resized = pyqtSignal(str, float, float, float, float)
    rotated = pyqtSignal(str, float)          # note_id, degrees
    interaction_finished = pyqtSignal(str)    # note_id — commit to the model

    HANDLE = 11          # drawn size of a corner/edge handle
    HIT = 13             # generous hit radius (bigger than the drawn dot)
    ROT_GAP = 34         # distance from the top edge to the rotation handle
    ROT_R = 9            # rotation handle radius
    MIN_W = 140
    MIN_H = 110
    SNAP_DEG = 15        # Shift-snap increment while rotating

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._note_id: str | None = None
        self._rect = QRectF()        # unrotated box in workspace (screen) coords
        self._angle = 0.0
        self._visible = False

        self._origin = QPointF(0, 0)  # our top-left in workspace coords
        self._mode = ""              # "" | "resize" | "rotate"
        self._active_handle = ""
        self._start_rect = QRectF()
        self._start_angle = 0.0
        self._grab_angle = 0.0
        self.hide()

    # ── State ────────────────────────────────────────────────────────────────

    def attach(self, note_id: str, rect: QRectF, angle: float):
        self._note_id = note_id
        self._rect = QRectF(rect)
        self._angle = angle
        self._visible = True
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._fit_to_content()
        self.show()
        self.raise_()
        self.update()

    def detach(self):
        self._note_id = None
        self._visible = False
        self.cancel_gesture()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()

    def cancel_gesture(self):
        """Abandon any in-flight resize/rotate and make sure no mouse grab is
        left behind. Safe to call at any time."""
        self._mode = ""
        self._active_handle = ""
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()

    def note_id(self) -> str | None:
        return self._note_id

    def is_busy(self) -> bool:
        """True while the user is actively resizing/rotating via this frame."""
        return bool(self._mode)

    def update_geometry(self, rect: QRectF, angle: float):
        """Follow the note (e.g. while it is being dragged by its body)."""
        self._rect = QRectF(rect)
        self._angle = angle
        self._fit_to_content()
        self.update()

    def _fit_to_content(self):
        """Shrink the widget to just the chrome it draws.

        The frame used to span the whole workspace, which made it the widget
        under EVERY click — it forwarded them on, but that put it in the path of
        all input and made one selected note feel like it owned the mouse. Sizing
        it to the rotated bounding box plus the rotation stem means Qt routes
        clicks elsewhere straight to the notes/canvas, and only genuine handle
        clicks reach us."""
        ws = self.parentWidget()
        if ws is None:
            return
        pts = [self._to_scene(p) for p in self._handle_points().values()]
        pts.append(self._to_scene(self._rot_point()))
        pad = self.HIT + 4
        left = min(p.x() for p in pts) - pad
        top = min(p.y() for p in pts) - pad
        right = max(p.x() for p in pts) + pad
        bottom = max(p.y() for p in pts) + pad
        # Clip to the workspace so the widget never extends outside its parent.
        left, top = max(0.0, left), max(0.0, top)
        right = min(float(ws.width()), right)
        bottom = min(float(ws.height()), bottom)
        self._origin = QPointF(left, top)
        self.setGeometry(int(left), int(top),
                         max(1, int(right - left)), max(1, int(bottom - top)))

    def wants(self, pos: QPointF) -> bool:
        """True when `pos` (WORKSPACE coords) is over one of our handles.

        The frame must PAINT across the whole workspace (outline, stem, handles)
        but must only RECEIVE clicks on its handles. A mask would solve the input
        half while clipping the painting, so instead the workspace asks this
        before routing a press, and we stay mouse-transparent the rest of the
        time."""
        return self._visible and bool(self._hit(pos - self._origin))

    def set_interactive(self, on: bool):
        """Kept for the workspace's hover call; the frame now stays interactive
        for as long as it is attached (see `attach`). Toggling transparency on
        hover was fragile: it required a mouse-move to land on the handle before
        the press, and after a rotation the handle slides out from under the
        cursor mid-gesture."""
        return

    # ── Geometry helpers ─────────────────────────────────────────────────────

    def _centre(self) -> QPointF:
        return self._rect.center()

    def _to_scene(self, p: QPointF) -> QPointF:
        return rotate(p, self._centre(), self._angle)

    def _to_local(self, p: QPointF) -> QPointF:
        return rotate(p, self._centre(), -self._angle)

    def _handle_points(self) -> dict[str, QPointF]:
        r = self._rect
        return {
            "NW": QPointF(r.left(),   r.top()),
            "N":  QPointF(r.center().x(), r.top()),
            "NE": QPointF(r.right(),  r.top()),
            "E":  QPointF(r.right(),  r.center().y()),
            "SE": QPointF(r.right(),  r.bottom()),
            "S":  QPointF(r.center().x(), r.bottom()),
            "SW": QPointF(r.left(),   r.bottom()),
            "W":  QPointF(r.left(),   r.center().y()),
        }

    def _rot_point(self) -> QPointF:
        r = self._rect
        return QPointF(r.center().x(), r.top() - self.ROT_GAP)

    # ── Painting ─────────────────────────────────────────────────────────────

    def paintEvent(self, e):
        if not self._visible or self._note_id is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # We draw in workspace coordinates; shift into our own local ones.
        p.translate(-self._origin)

        pts = {k: self._to_scene(v) for k, v in self._handle_points().items()}

        # Outline, following the rotated box.
        poly = QPolygonF([pts["NW"], pts["NE"], pts["SE"], pts["SW"]])
        p.setPen(QPen(ACCENT, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(poly)

        # Stem + rotation handle above the top edge.
        rot = self._to_scene(self._rot_point())
        top_mid = pts["N"]
        p.drawLine(top_mid, rot)
        p.setBrush(QBrush(HANDLE_FILL))
        p.drawEllipse(rot, self.ROT_R, self.ROT_R)
        # Little curved arrow inside the knob.
        p.setPen(QPen(ACCENT, 1.4))
        arc = QRectF(rot.x() - 4, rot.y() - 4, 8, 8)
        p.drawArc(arc, 40 * 16, 260 * 16)

        # Corner dots (circles) and edge grips (capsules), as in the reference.
        p.setPen(QPen(ACCENT, 1.5))
        p.setBrush(QBrush(HANDLE_FILL))
        h = self.HANDLE
        for key in CORNERS:
            p.drawEllipse(pts[key], h / 2, h / 2)
        for key in EDGES:
            # Capsule oriented along its edge, rotated with the note.
            p.save()
            p.translate(pts[key])
            p.rotate(self._angle + (90 if key in ("E", "W") else 0))
            p.drawRoundedRect(QRectF(-h * 1.1, -h / 3.2, h * 2.2, h / 1.6),
                              h / 3.2, h / 3.2)
            p.restore()

    # ── Hit-testing ──────────────────────────────────────────────────────────

    def _hit(self, pos: QPointF) -> str:
        """Which handle is under `pos` (LOCAL widget coords)? Returns "" for
        none, "ROT" for the rotation knob, else a compass key."""
        if not self._visible:
            return ""
        pos = pos + self._origin          # -> workspace coords
        rot = self._to_scene(self._rot_point())
        if math.hypot(pos.x() - rot.x(), pos.y() - rot.y()) <= self.ROT_R + 5:
            return "ROT"
        for key, local in self._handle_points().items():
            sp = self._to_scene(local)
            if math.hypot(pos.x() - sp.x(), pos.y() - sp.y()) <= self.HIT:
                return key
        return ""

    def cursor_for(self, handle: str) -> QCursor:
        if handle == "ROT":
            return QCursor(Qt.CursorShape.CrossCursor)
        if handle not in _BASE_ANGLE:
            return QCursor(Qt.CursorShape.ArrowCursor)
        # Rotate the handle's compass direction by the note's angle, then pick
        # the nearest 45° octant so the arrow always points the right way.
        deg = (_BASE_ANGLE[handle] - self._angle) % 180
        octant = int((deg + 22.5) // 45) % 4
        return QCursor(_CURSOR_BY_OCTANT[octant])

    # ── Interaction ──────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self._visible:
            e.ignore()
            return
        handle = self._hit(e.position())
        if not handle:
            # Not on a handle → hand the press to the workspace underneath.
            # `e.ignore()` alone would NOT reach a sibling widget.
            self._forward_to_workspace(e)
            return

        self._active_handle = handle
        self._start_rect = QRectF(self._rect)
        self._start_angle = self._angle
        # NOTE: deliberately NO grabMouse() here. Qt's implicit grab already
        # delivers the rest of the drag to whichever widget accepted the press,
        # and an explicit grab that outlives the gesture (cursor leaves, a dialog
        # opens, a repaint moves the handle) freezes every click in the app.
        if handle == "ROT":
            self._mode = "rotate"
            c = self._centre()
            sp = e.position() + self._origin      # -> workspace coords
            self._grab_angle = math.degrees(
                math.atan2(sp.y() - c.y(), sp.x() - c.x())
            )
        else:
            self._mode = "resize"
        e.accept()

    def _forward_to_workspace(self, e):
        """Re-dispatch a press/move/release we do not want to the workspace.

        Our coordinates are local to this widget, which no longer covers the
        whole workspace, so shift them back before handing the event on.
        """
        ws = self.parentWidget()
        if ws is None:
            e.ignore()
            return
        from PyQt6.QtGui import QMouseEvent
        sp = e.position() + self._origin
        e = QMouseEvent(e.type(), sp, e.globalPosition(), e.button(),
                        e.buttons(), e.modifiers())
        handler = {
            QEvent.Type.MouseButtonPress: ws.mousePressEvent,
            QEvent.Type.MouseMove: ws.mouseMoveEvent,
            QEvent.Type.MouseButtonRelease: ws.mouseReleaseEvent,
            QEvent.Type.MouseButtonDblClick: ws.mouseDoubleClickEvent,
        }.get(e.type())
        if handler is None:
            e.ignore()
            return
        handler(e)
        e.accept()

    def mouseMoveEvent(self, e):
        if self._mode == "resize":
            self._do_resize(e.position() + self._origin)
            e.accept()
            return
        if self._mode == "rotate":
            self._do_rotate(e.position() + self._origin, e.modifiers())
            e.accept()
            return
        # Idle: show the right cursor over handles, and pass everything else to
        # the workspace so notes still get their hover/drag behaviour.
        handle = self._hit(e.position())
        if handle:
            self.setCursor(self.cursor_for(handle))
            e.accept()
            return
        self.unsetCursor()
        self._forward_to_workspace(e)

    def mouseReleaseEvent(self, e):
        if self._mode:
            self._mode = ""
            self._active_handle = ""
            if self._note_id:
                self.interaction_finished.emit(self._note_id)
            e.accept()
            return
        self._forward_to_workspace(e)

    def mouseDoubleClickEvent(self, e):
        if self._hit(e.position()):
            e.accept()
            return
        self._forward_to_workspace(e)

    def _do_resize(self, pos: QPointF):
        """Resize in the note's LOCAL space so dragging a handle on a rotated
        note moves the edge the handle actually sits on."""
        d = self._active_handle
        start = self._start_rect
        centre = start.center()
        # Map the cursor into the unrotated frame of the note as it was on press.
        local = rotate(pos, centre, -self._start_angle)

        left, top = start.left(), start.top()
        right, bottom = start.right(), start.bottom()
        if "N" in d:
            top = min(local.y(), bottom - self.MIN_H)
        if "S" in d:
            bottom = max(local.y(), top + self.MIN_H)
        if "W" in d:
            left = min(local.x(), right - self.MIN_W)
        if "E" in d:
            right = max(local.x(), left + self.MIN_W)
        new_local = QRectF(QPointF(left, top), QPointF(right, bottom))

        # Resizing moves the box's centre; rotation is about the centre, so the
        # anchored edge would drift. Correct by rotating the centre offset.
        new_centre = new_local.center()
        corrected = rotate(new_centre, centre, self._start_angle)
        new_local.moveCenter(corrected)

        self._rect = new_local
        self.update()
        self.resized.emit(self._note_id, new_local.x(), new_local.y(),
                          new_local.width(), new_local.height())

    def _do_rotate(self, pos: QPointF, modifiers):
        c = self._centre()
        now = math.degrees(math.atan2(pos.y() - c.y(), pos.x() - c.x()))
        angle = self._start_angle + (now - self._grab_angle)
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            angle = round(angle / self.SNAP_DEG) * self.SNAP_DEG
        self._angle = angle % 360.0
        self.update()
        self.rotated.emit(self._note_id, self._angle)
