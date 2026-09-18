"""
HSV colour-wheel + value/alpha-style bar widgets used by the colour panel.

`ColorWheel` — hue around the circumference, saturation along the radius.
`ValueBar`   — vertical brightness ramp for the current hue/saturation.

Both emit `color_changed(QColor)` while dragging and expose `set_color()` so the
panel can keep them in sync with numeric fields.
"""

import math

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QConicalGradient, QRadialGradient, QLinearGradient,
    QPen, QBrush,
)


class ColorWheel(QWidget):
    """Hue/saturation wheel. Value (brightness) is supplied externally."""

    color_changed = pyqtSignal(QColor)

    def __init__(self, diameter: int = 150, parent=None):
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self._hue = 0.0          # 0..1
        self._sat = 0.0          # 0..1
        self._val = 1.0          # 0..1
        self._dragging = False

    # ── State ─────────────────────────────────────────────────────────────────

    def color(self) -> QColor:
        return QColor.fromHsvF(self._hue, self._sat, self._val)

    def set_color(self, c: QColor):
        h, s, v, _ = c.getHsvF()
        self._hue = max(0.0, h)  # getHsvF returns -1 hue for greys
        self._sat = s
        self._val = v
        self.update()

    def set_value(self, v: float):
        self._val = max(0.0, min(1.0, v))
        self.update()

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        # Hue ring (conical) then white-to-transparent radial for saturation.
        # QConicalGradient sweeps counter-clockwise from its start angle, but the
        # picker/marker map hue clockwise from 12 o'clock (Qt's y axis points
        # down). Feed the stops in reverse so painted hue == picked hue.
        # Sample finely: RGB-interpolating between distant hues would otherwise
        # cut through desaturated colours between stops.
        hue_grad = QConicalGradient(rect.center(), 90)
        for i in range(0, 361, 10):
            hue_grad.setColorAt(i / 360.0, QColor.fromHsvF(((360 - i) % 360) / 360.0, 1, 1))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(hue_grad))
        p.drawEllipse(rect)

        sat_grad = QRadialGradient(rect.center(), rect.width() / 2)
        sat_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
        sat_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(sat_grad))
        p.drawEllipse(rect)

        # Darken the whole wheel to reflect the current brightness.
        if self._val < 1.0:
            p.setBrush(QColor(0, 0, 0, int((1.0 - self._val) * 255)))
            p.drawEllipse(rect)

        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # Selection marker. Must use the same mapping as _pick(): QConicalGradient
        # sweeps counter-clockwise from 12 o'clock, while Qt's y axis points down,
        # so screen-y is negated to keep marker and picker on the same hue.
        c = rect.center()
        r = rect.width() / 2 * self._sat
        angle = self._hue * 2 * math.pi
        mx = c.x() + r * math.sin(angle)
        my = c.y() - r * math.cos(angle)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QPointF(mx, my), 6, 6)

    # ── Interaction ───────────────────────────────────────────────────────────

    def _pick(self, pos):
        rect = QRectF(self.rect())
        c = rect.center()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        radius = rect.width() / 2
        dist = math.hypot(dx, dy)
        self._sat = min(1.0, dist / radius) if radius else 0.0
        # Inverse of the marker mapping above: dx = sin(a), dy = -cos(a).
        angle = math.atan2(dx, -dy)
        self._hue = (angle / (2 * math.pi)) % 1.0
        self.update()
        self.color_changed.emit(self.color())

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._pick(e.position())
            e.accept()

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._pick(e.position())
            e.accept()

    def mouseReleaseEvent(self, e):
        self._dragging = False
        super().mouseReleaseEvent(e)


class ValueBar(QWidget):
    """Vertical brightness ramp for the current hue/saturation."""

    value_changed = pyqtSignal(float)

    def __init__(self, width: int = 18, height: int = 150, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._hue = 0.0
        self._sat = 0.0
        self._val = 1.0
        self._dragging = False

    def set_color(self, c: QColor):
        h, s, v, _ = c.getHsvF()
        self._hue = max(0.0, h)
        self._sat = s
        self._val = v
        self.update()

    def value(self) -> float:
        return self._val

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, QColor.fromHsvF(self._hue, self._sat, 1.0))
        grad.setColorAt(1.0, QColor(0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(rect, 3, 3)

        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 3, 3)

        y = rect.top() + (1.0 - self._val) * rect.height()
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

    def _pick(self, pos):
        h = max(1, self.height())
        self._val = max(0.0, min(1.0, 1.0 - pos.y() / h))
        self.update()
        self.value_changed.emit(self._val)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._pick(e.position())
            e.accept()

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._pick(e.position())
            e.accept()

    def mouseReleaseEvent(self, e):
        self._dragging = False
        super().mouseReleaseEvent(e)
