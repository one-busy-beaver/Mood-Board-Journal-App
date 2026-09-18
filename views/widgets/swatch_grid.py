"""
Reorderable swatch grid for the colour panel's Saved page.

Swatches are positioned absolutely (no QLayout) so a dragged chip can float
freely without fighting a layout manager. The remaining chips animate into their
new slots as the drag crosses them — iOS home-screen style — so the gap opens up
live rather than snapping on drop.

- Left click selects; left click-and-hold drags to rearrange.
- Right click opens a small "Delete" confirm centred on the swatch; clicking
  anywhere else cancels it.
"""

from PyQt6.QtWidgets import QWidget, QPushButton
from PyQt6.QtCore import (
    Qt, pyqtSignal, QPoint, QSize, QRectF, QTimer, QPropertyAnimation, QEasingCurve,
    QParallelAnimationGroup, QAbstractAnimation,
)
from PyQt6.QtGui import QPainter, QPen, QColor

SWATCH = 30
GAP = 8
COLS = 6
CELL = SWATCH + GAP
DRAG_THRESHOLD = 5   # px before a press becomes a drag
ANIM_MS = 160


class _Swatch(QPushButton):
    """One colour chip. Absolutely positioned by its parent SwatchGrid."""

    picked = pyqtSignal(str)
    delete_requested = pyqtSignal(str, QPoint)
    drag_started = pyqtSignal(object)
    drag_moved = pyqtSignal(object, QPoint)
    drag_ended = pyqtSignal(object)

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._press_pos: QPoint | None = None
        self._grab_offset = QPoint()
        self._dragging = False

        self.setFixedSize(SWATCH, SWATCH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(color)
        self._apply_style()

    @property
    def color(self) -> str:
        return self._color

    def set_lifted(self, lifted: bool):
        """Visual state while dragging. Uses opacity rather than a stylesheet
        swap — restyling mid-drag forces a synchronous style/paint pass that can
        re-enter event delivery and crash on Windows."""
        self.setWindowOpacity(0.85 if lifted else 1.0)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QPushButton {{ background: {self._color};
                           border: 1px solid rgba(255,255,255,0.25);
                           border-radius: 6px; }}
            QPushButton:hover {{ border: 2px solid #fafaf9; }}
        """)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            centre = self.mapToGlobal(QPoint(self.width() // 2, self.height() // 2))
            self.delete_requested.emit(self._color, centre)
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.position().toPoint()
            self._grab_offset = e.position().toPoint()
            self._dragging = False
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press_pos is None:
            return
        if not self._dragging:
            if (e.position().toPoint() - self._press_pos).manhattanLength() < DRAG_THRESHOLD:
                return
            self._dragging = True
            self.raise_()
            self.drag_started.emit(self)

        parent = self.parentWidget()
        if parent is not None and self.isVisible():
            pos = parent.mapFromGlobal(e.globalPosition().toPoint()) - self._grab_offset
            old = self.geometry()
            # Notify BEFORE moving: the handler may reorder/animate siblings, and
            # move() can flush paint events. Doing it in this order keeps the
            # widget's own state settled before anything re-enters.
            self.drag_moved.emit(self, pos)
            self.move(pos)
            # Explicitly repaint the vacated rect — Qt does not always invalidate
            # it for a moving child, leaving smear trails.
            parent.update(old)
        e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._press_pos is None:
            return super().mouseReleaseEvent(e)
        was_drag = self._dragging
        self._press_pos = None
        self._dragging = False
        self.set_lifted(False)
        if was_drag:
            self.drag_ended.emit(self)
        else:
            self.picked.emit(self._color)
        e.accept()


class DeleteConfirm(QWidget):
    """Confirm bubble sitting above a swatch, with a tail pointing down at it.

    Custom-painted (rounded body + triangle) rather than a styled QFrame so the
    tail is part of the same shape.
    """

    confirmed = pyqtSignal()

    TAIL_W = 12
    TAIL_H = 7
    PAD_X = 8
    PAD_Y = 6
    RADIUS = 8
    GAP = 6      # space between the tail tip and the swatch

    def __init__(self, parent: QWidget, swatch_centre_global: QPoint,
                 swatch_half_h: int):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._btn = QPushButton("Delete", self)
        self._btn.setFixedHeight(24)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setStyleSheet("""
            QPushButton { background: #dc2626; color: white; border: none;
                          border-radius: 5px; font-size: 11px; font-weight: 600;
                          padding: 0 14px; }
            QPushButton:hover { background: #b91c1c; }
        """)
        self._btn.clicked.connect(self.confirmed.emit)
        self._btn.adjustSize()

        w = self._btn.width() + self.PAD_X * 2
        h = self._btn.height() + self.PAD_Y * 2 + self.TAIL_H
        self.setFixedSize(w, h)
        self._btn.move(self.PAD_X, self.PAD_Y)

        # Anchor: centred horizontally on the swatch, body sitting above it with
        # the tail tip just touching the swatch's top edge.
        local = parent.mapFromGlobal(swatch_centre_global)
        self._tail_x = w // 2          # tail centre within our own coords
        x = local.x() - w // 2
        y = local.y() - swatch_half_h - self.GAP - h

        # Keep the bubble on screen, but clamp to the WINDOW rather than the
        # swatch grid's card: the bubble is allowed to float outside the card
        # (it is hosted on the panel's full-window layer, see _bubble_host), so
        # clamping to the card would squash it against the card's top edge.
        cx = max(4, min(x, parent.width() - w - 4))
        cy = max(4, min(y, parent.height() - h - 4))
        # Re-aim the tail so it still points at the swatch after any clamping.
        self._tail_x = max(self.RADIUS + self.TAIL_W // 2,
                           min(local.x() - cx, w - self.RADIUS - self.TAIL_W // 2))
        self.move(cx, cy)
        self.show()
        self.raise_()

    def paintEvent(self, e):
        from PyQt6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        body = QRectF(0, 0, self.width(), self.height() - self.TAIL_H)
        path = QPainterPath()
        path.addRoundedRect(body, self.RADIUS, self.RADIUS)

        # Downward tail
        tail = QPainterPath()
        tail.moveTo(self._tail_x - self.TAIL_W / 2, body.bottom() - 0.5)
        tail.lineTo(self._tail_x, self.height())
        tail.lineTo(self._tail_x + self.TAIL_W / 2, body.bottom() - 0.5)
        tail.closeSubpath()
        path = path.united(tail)

        p.setPen(QPen(QColor("#57534e"), 1))
        p.setBrush(QColor("#1c1917"))
        p.drawPath(path)


class SwatchGrid(QWidget):
    """Left-aligned, animated, reorderable grid of colour swatches."""

    picked = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    reordered = pyqtSignal(str, int)
    rebuild_requested = pyqtSignal()   # a deferred rebuild needs fresh model state

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._swatches: list[_Swatch] = []   # visual order
        self._drag_from: int | None = None   # index the dragged chip came from
        self._anims: QParallelAnimationGroup | None = None
        self._confirm: DeleteConfirm | None = None
        self._pending_colors: list[str] | None = None  # rebuild deferred past a drag

    # ── Geometry helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _slot_pos(index: int) -> QPoint:
        return QPoint((index % COLS) * CELL, (index // COLS) * CELL)

    def _rows(self, count: int) -> int:
        return max(1, (max(0, count - 1) // COLS) + 1)

    def sizeHint(self) -> QSize:
        rows = self._rows(len(self._swatches))
        return QSize(COLS * CELL - GAP, rows * CELL - GAP)

    def _update_height(self):
        self.setMinimumHeight(self.sizeHint().height())
        self.updateGeometry()

    # ── Population ────────────────────────────────────────────────────────────

    def set_colors(self, colors: list[str]):
        # A rebuild while a chip is mid-drag would delete the widget that is
        # still delivering mouse events (native crash). Defer instead.
        if self._drag_from is not None:
            self._pending_colors = list(colors)
            return

        self._stop_anims()
        self._dismiss_confirm()
        for sw in self._swatches:
            sw.setParent(None)
            sw.deleteLater()
        self._swatches = []

        for color in colors:
            sw = _Swatch(color, self)
            sw.picked.connect(self.picked.emit)
            sw.delete_requested.connect(self._show_confirm)
            sw.drag_started.connect(self._on_drag_started)
            sw.drag_moved.connect(self._on_drag_moved)
            sw.drag_ended.connect(self._on_drag_ended)
            self._swatches.append(sw)
            sw.show()

        self._layout_swatches(animate=False)
        self._update_height()

    def _layout_swatches(self, animate: bool, skip: _Swatch | None = None):
        """Move every chip to its slot — animated for the iOS-style shuffle."""
        self._stop_anims()
        group = QParallelAnimationGroup(self)
        for i, sw in enumerate(list(self._swatches)):
            if sw is skip:
                continue           # the dragged chip follows the cursor instead
            target = self._slot_pos(i)
            if sw.pos() == target:
                continue
            if not animate:
                sw.move(target)
                continue
            a = QPropertyAnimation(sw, b"pos", self)
            a.setDuration(ANIM_MS)
            a.setStartValue(sw.pos())
            a.setEndValue(target)
            a.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(a)
        if group.animationCount():
            self._anims = group
            # KeepWhenStopped: with DeleteWhenStopped Qt frees the group the moment
            # it finishes, leaving self._anims dangling and crashing the next
            # _stop_anims(). We own it and drop it explicitly instead.
            group.finished.connect(lambda g=group: self._on_anims_finished(g))
            group.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)
        else:
            group.deleteLater()

    def _on_anims_finished(self, group):
        if self._anims is group:
            self._anims = None
        group.deleteLater()

    def _stop_anims(self):
        group, self._anims = self._anims, None
        if group is None:
            return
        try:
            group.stop()
            group.deleteLater()
        except RuntimeError:
            pass  # already destroyed by Qt

    # ── Drag reorder (iOS-style live gap) ─────────────────────────────────────

    def _on_drag_started(self, sw: _Swatch):
        self._dismiss_confirm()
        if sw in self._swatches:
            self._drag_from = self._swatches.index(sw)

    def _on_drag_moved(self, sw: _Swatch, pos: QPoint):
        """As the chip crosses a slot, reorder the list and animate the rest so
        the gap opens where it will land."""
        if sw not in self._swatches or not self._swatches:
            return
        centre = pos + QPoint(SWATCH // 2, SWATCH // 2)
        col = max(0, min(COLS - 1, round(centre.x() / CELL - 0.5)))
        row = max(0, round(centre.y() / CELL - 0.5))
        target = min(len(self._swatches) - 1, int(row * COLS + col))

        current = self._swatches.index(sw)
        if target != current:
            self._swatches.insert(target, self._swatches.pop(current))
            self._layout_swatches(animate=True, skip=sw)

    def _on_drag_ended(self, sw: _Swatch):
        from_index, self._drag_from = self._drag_from, None
        color = sw.color if sw in self._swatches else None
        new_index = self._swatches.index(sw) if color is not None else None

        # Everything below runs while mouseReleaseEvent is still on the stack.
        # Starting animations / rebuilding the grid here can destroy or repaint
        # the widget that is mid-event, so defer to the next event-loop turn.
        def settle():
            self._layout_swatches(animate=True)
            if color is not None and from_index is not None and new_index != from_index:
                self.reordered.emit(color, new_index)
            # A rebuild requested during the drag used a pre-reorder snapshot, so
            # ask for fresh model state rather than replaying a stale list.
            if self._pending_colors is not None:
                self._pending_colors = None
                self.rebuild_requested.emit()

        QTimer.singleShot(0, settle)

    # ── Delete confirm ────────────────────────────────────────────────────────

    def _show_confirm(self, color: str, centre_global: QPoint):
        self._dismiss_confirm()
        if not self.isVisible():
            return
        # Parent to the panel's full-window layer — NOT the card (Qt clips
        # children to their parent, which squashed the bubble against the card's
        # top edge) and NOT self.window() (a bubble parented to the main window
        # outlives the panel and is left orphaned when the panel closes).
        host = self._bubble_host()
        if host is None:
            return
        bubble = DeleteConfirm(host, centre_global, SWATCH // 2)
        bubble.confirmed.connect(lambda: self._confirm_delete(color))
        self._confirm = bubble
        win = self.window()
        if win is not None:
            win.installEventFilter(self)

    def _bubble_host(self) -> QWidget | None:
        """The panel/overlay widget this grid lives in.

        This is the full-window layer *inside* the panel (BasePanel/BaseOverlay),
        one level above "panelCard". Hosting the bubble here means it can draw
        outside the card without being clipped, while still being destroyed
        together with the panel rather than orphaned on the main window."""
        w = self.parentWidget()
        host = None
        card = None
        while w is not None:
            if w.objectName() == "panelCard":
                card = w
            elif card is not None:
                # First ancestor above the card = the panel's own full-window layer.
                return w
            host = w
            w = w.parentWidget()
        return host

    def _confirm_delete(self, color: str):
        self._dismiss_confirm()
        self.delete_requested.emit(color)

    def _dismiss_confirm(self):
        if self._confirm is not None:
            try:
                self._confirm.hide()
                self._confirm.deleteLater()
            except RuntimeError:
                pass  # already destroyed with its parent
            self._confirm = None
        win = self.window()
        if win is not None:
            win.removeEventFilter(self)

    def hideEvent(self, e):
        # Panel closed / tab switched away — never leave a bubble behind.
        self._dismiss_confirm()
        super().hideEvent(e)

    def eventFilter(self, obj, event):
        if self._confirm is not None and event.type() == event.Type.MouseButtonPress:
            pos = self._confirm.mapFromGlobal(event.globalPosition().toPoint())
            if not self._confirm.rect().contains(pos):
                self._dismiss_confirm()
        return super().eventFilter(obj, event)
