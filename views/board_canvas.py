from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QKeyEvent


class BoardScene(QGraphicsScene):
    create_note_requested = pyqtSignal(float, float)

    def __init__(self):
        super().__init__()
        self.setSceneRect(-5000, -5000, 10000, 10000)

    def mouseDoubleClickEvent(self, e):
        # Only create a note if the double-click lands on the background
        view = self.views()[0] if self.views() else None
        transform = view.transform() if view else self.views()[0].transform()
        item = self.itemAt(e.scenePos(), transform)
        if item is None:
            self.create_note_requested.emit(e.scenePos().x(), e.scenePos().y())
        super().mouseDoubleClickEvent(e)


class BoardCanvas(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = BoardScene()
        self.setScene(self._scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor("#1c1917")))

        self._panning = False
        self._pan_origin = None

        self._zoom = 1.0
        self._zoom_min = 0.25
        self._zoom_max = 3.0

    @property
    def scene(self) -> BoardScene:
        return self._scene

    # ── Zoom ─────────────────────────────────────────────────────────────────

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        factor = 1.12 if delta > 0 else 1 / 1.12
        new_zoom = self._zoom * factor
        if self._zoom_min <= new_zoom <= self._zoom_max:
            self._zoom = new_zoom
            self.scale(factor, factor)

    # ── Pan (middle mouse or Space+drag) ─────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_origin = e.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._panning and self._pan_origin is not None:
            delta = e.position().toPoint() - self._pan_origin
            self._pan_origin = e.position().toPoint()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._panning and e.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self._pan_origin = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e: QKeyEvent):
        # Let arrow keys propagate to MainWindow shortcuts instead of scrolling the view
        if e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right):
            e.ignore()
            return
        super().keyPressEvent(e)

    # ── Dot-grid background ───────────────────────────────────────────────────

    def drawBackground(self, painter: QPainter, rect):
        super().drawBackground(painter, rect)

        grid = 40
        dot_color = QColor(255, 255, 255, 22)
        painter.setPen(QPen(dot_color, 1.5))

        left = int(rect.left()) - (int(rect.left()) % grid)
        top = int(rect.top()) - (int(rect.top()) % grid)
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                painter.drawPoint(x, y)
                y += grid
            x += grid
