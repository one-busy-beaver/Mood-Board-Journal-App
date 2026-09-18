"""Colour-picking surfaces for the colour panel (Colors-app style).

Three interchangeable modes, each a self-contained widget:

  `DiscPicker`    hue ring + saturation/brightness triangle-square inside it
  `ClassicPicker` saturation/brightness rectangle + hue and brightness sliders
  `ValuePicker`   H/S/B and R/G/B sliders with numeric readouts

**Colour-maths contract.** Every mode stores HSV internally (`_h`, `_s`, `_v`
in 0..1) and is the single source of truth for the colour it emits. Painting and
hit-testing use the *same* mapping in both directions, so the swatch, the marker
position and the hex string can never disagree:

  - Hue is measured clockwise from 12 o'clock. Qt's y axis points down, so the
    forward map is  x = cx + r·sin(2πh),  y = cy − r·cos(2πh)  and the inverse
    is  h = atan2(dx, −dy) / 2π  (mod 1).
  - Greys have no hue: `QColor.getHsvF()` returns −1, which would otherwise
    reset the ring to red. `_set_hsv` keeps the previous hue in that case.
  - Colours are emitted via `QColor.fromHsvF`, and the panel converts to hex
    with `.name()`, so a value shown as #RRGGBB is exactly the colour painted.
"""

import math

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF, QSize
from PyQt6.QtGui import (
    QPainter, QColor, QConicalGradient, QLinearGradient, QPen, QBrush, QImage,
)

# Shared chrome
_MARKER_PEN = QColor("#ffffff")
_EDGE_PEN = QColor(0, 0, 0, 70)


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


class _HsvPicker(QWidget):
    """Common HSV state + change signalling for every picker mode."""

    color_changed = pyqtSignal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._h = 0.0
        self._s = 1.0
        self._v = 1.0
        self._emitting = False

    # ── State ────────────────────────────────────────────────────────────────

    def color(self) -> QColor:
        return QColor.fromHsvF(self._h, self._s, self._v)

    def set_color(self, c: QColor):
        """Adopt an externally-set colour without re-emitting a change."""
        h, s, v, _ = c.getHsvF()
        # Grey/black have undefined hue (-1); keep the ring where the user left it
        # instead of snapping to red.
        self._h = self._h if h < 0 else h
        self._s = clamp01(s)
        self._v = clamp01(v)
        self.update()

    def _emit(self):
        self.update()
        self.color_changed.emit(self.color())

    # ── Painting helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _draw_marker(p: QPainter, pos: QPointF, radius: float = 7.0,
                     fill: QColor | None = None):
        p.setPen(QPen(_MARKER_PEN, 2))
        p.setBrush(QBrush(fill) if fill is not None else Qt.BrushStyle.NoBrush)
        p.drawEllipse(pos, radius, radius)
        # Thin dark outline keeps the marker visible on light colours.
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        p.drawEllipse(pos, radius + 1, radius + 1)


# ── Mode 1: Disc — hue ring with an SV square inside ─────────────────────────

class DiscPicker(_HsvPicker):
    """Hue ring around a saturation/brightness square.

    The ring sets hue; the inner square sets saturation (x) and brightness (y),
    so every colour of that hue is reachable without a separate slider.
    """

    RING = 22          # ring thickness
    GAP = 8            # space between ring and inner square

    def __init__(self, size: int = 208, parent=None):
        super().__init__(parent)
        self.setMinimumSize(size, size)
        self._drag = None      # "ring" | "square" | None
        self._sv_cache: QImage | None = None
        self._sv_cache_hue = -1.0

    def sizeHint(self) -> QSize:
        return QSize(self.minimumWidth(), self.minimumHeight())

    # ── Geometry (one definition, used by both paint and hit-test) ───────────

    def _disc_rect(self) -> QRectF:
        side = min(self.width(), self.height())
        return QRectF((self.width() - side) / 2.0, (self.height() - side) / 2.0,
                      side, side).adjusted(1, 1, -1, -1)

    def _square_rect(self) -> QRectF:
        """Largest square that fits inside the ring, with GAP clearance.

        A square inscribed in a circle of radius r has side r·√2, so the
        half-diagonal is exactly r — the corners touch the circle. The clearance
        must therefore come off the radius *before* the √2 conversion, or the
        corners ride over the hue ring.
        """
        d = self._disc_rect()
        inner_r = max(1.0, d.width() / 2.0 - self.RING - self.GAP)
        side = inner_r * math.sqrt(2.0)
        c = d.center()
        return QRectF(c.x() - side / 2.0, c.y() - side / 2.0, side, side)

    # ── Paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = self._disc_rect()

        # Hue ring. QConicalGradient sweeps counter-clockwise from its start
        # angle while our hue runs clockwise from 12 o'clock, so feed the stops
        # reversed — this is what keeps painted hue == picked hue.
        grad = QConicalGradient(d.center(), 90)
        for i in range(0, 361, 5):
            grad.setColorAt(i / 360.0, QColor.fromHsvF(((360 - i) % 360) / 360.0, 1, 1))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(d)

        # Punch out the middle to leave a ring.
        inner = d.adjusted(self.RING, self.RING, -self.RING, -self.RING)
        p.setBrush(QColor("#2b2724"))
        p.drawEllipse(inner)

        p.setPen(QPen(_EDGE_PEN, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(d)
        p.drawEllipse(inner)

        # SV square for the current hue.
        sq = self._square_rect()
        p.drawImage(sq, self._sv_image(sq.size().toSize()))
        p.setPen(QPen(_EDGE_PEN, 1))
        p.drawRect(sq)

        # Ring marker at the current hue, on the ring's centreline.
        rr = (d.width() / 2.0) - self.RING / 2.0
        c = d.center()
        a = self._h * 2 * math.pi
        self._draw_marker(p, QPointF(c.x() + rr * math.sin(a),
                                     c.y() - rr * math.cos(a)),
                          radius=self.RING / 2.0 - 2,
                          fill=QColor.fromHsvF(self._h, 1, 1))

        # Square marker at (saturation, brightness).
        self._draw_marker(p, QPointF(sq.left() + self._s * sq.width(),
                                     sq.top() + (1.0 - self._v) * sq.height()),
                          fill=self.color())

    def _sv_image(self, size: QSize) -> QImage:
        """Saturation (x) × brightness (y) plane for the current hue.

        Rendered per-pixel and cached per hue: a two-gradient approximation
        composites in sRGB and would not match `QColor.fromHsvF` exactly, which
        is what the numbers and the swatch report.
        """
        w, h = max(1, size.width()), max(1, size.height())
        if (self._sv_cache is not None and self._sv_cache_hue == self._h
                and self._sv_cache.size() == QSize(w, h)):
            return self._sv_cache
        img = QImage(w, h, QImage.Format.Format_RGB32)
        for y in range(h):
            v = 1.0 - (y / (h - 1) if h > 1 else 0.0)
            for x in range(w):
                s = x / (w - 1) if w > 1 else 0.0
                img.setPixelColor(x, y, QColor.fromHsvF(self._h, s, v))
        self._sv_cache = img
        self._sv_cache_hue = self._h
        return img

    # ── Interaction ──────────────────────────────────────────────────────────

    def _hit(self, pos: QPointF) -> str:
        d = self._disc_rect()
        c = d.center()
        dist = math.hypot(pos.x() - c.x(), pos.y() - c.y())
        outer = d.width() / 2.0
        if dist >= outer - self.RING - 1:
            return "ring"
        if self._square_rect().contains(pos):
            return "square"
        return ""

    def _apply(self, pos: QPointF, where: str):
        if where == "ring":
            d = self._disc_rect()
            c = d.center()
            # Exact inverse of the ring-marker mapping above.
            self._h = (math.atan2(pos.x() - c.x(), -(pos.y() - c.y()))
                       / (2 * math.pi)) % 1.0
        elif where == "square":
            sq = self._square_rect()
            self._s = clamp01((pos.x() - sq.left()) / sq.width())
            self._v = clamp01(1.0 - (pos.y() - sq.top()) / sq.height())
        else:
            return
        self._emit()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = self._hit(e.position())
            if self._drag:
                self._apply(e.position(), self._drag)
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag:
            self._apply(e.position(), self._drag)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)


# ── Mode 2: Classic — SV rectangle + hue / brightness sliders ────────────────

class _Slider(QWidget):
    """A flat gradient slider. The gradient is supplied by the owner so the same
    widget serves hue, brightness and R/G/B channels."""

    value_changed = pyqtSignal(float)

    H = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.H)
        self.setMinimumWidth(60)
        self._value = 1.0
        self._stops: list[tuple[float, QColor]] = [(0.0, QColor("#000")),
                                                   (1.0, QColor("#fff"))]
        self._drag = False

    def set_stops(self, stops: list[tuple[float, QColor]]):
        self._stops = stops
        self.update()

    def set_value(self, v: float):
        self._value = clamp01(v)
        self.update()

    def value(self) -> float:
        return self._value

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 3.5, -0.5, -3.5)
        grad = QLinearGradient(r.topLeft(), r.topRight())
        for at, col in self._stops:
            grad.setColorAt(at, col)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(QPen(_EDGE_PEN, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)

        x = r.left() + self._value * r.width()
        knob = QPointF(x, r.center().y())
        p.setPen(QPen(_MARKER_PEN, 2))
        p.setBrush(QColor(0, 0, 0, 30))
        p.drawEllipse(knob, 6, 6)

    def _pick(self, pos: QPointF):
        r = QRectF(self.rect()).adjusted(0.5, 0, -0.5, 0)
        self._value = clamp01((pos.x() - r.left()) / max(1.0, r.width()))
        self.update()
        self.value_changed.emit(self._value)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            self._pick(e.position())
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag:
            self._pick(e.position())
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = False
        super().mouseReleaseEvent(e)


class _SVPlane(QWidget):
    """Saturation (x) × brightness (y) rectangle for a fixed hue."""

    changed = pyqtSignal(float, float)   # s, v

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self._h = 0.0
        self._s = 1.0
        self._v = 1.0
        self._drag = False
        self._cache: QImage | None = None
        self._cache_key = None

    def set_hsv(self, h: float, s: float, v: float):
        self._h, self._s, self._v = h, s, v
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = QRectF(self.rect())
        p.drawImage(r, self._image(r.size().toSize()))
        p.setPen(QPen(_EDGE_PEN, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))

        pos = QPointF(r.left() + self._s * r.width(),
                      r.top() + (1.0 - self._v) * r.height())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(_MARKER_PEN, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(pos, 7, 7)
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        p.drawEllipse(pos, 8, 8)

    def _image(self, size: QSize) -> QImage:
        w, h = max(1, size.width()), max(1, size.height())
        key = (self._h, w, h)
        if self._cache is not None and self._cache_key == key:
            return self._cache
        img = QImage(w, h, QImage.Format.Format_RGB32)
        for y in range(h):
            v = 1.0 - (y / (h - 1) if h > 1 else 0.0)
            for x in range(w):
                s = x / (w - 1) if w > 1 else 0.0
                img.setPixelColor(x, y, QColor.fromHsvF(self._h, s, v))
        self._cache = img
        self._cache_key = key
        return img

    def _pick(self, pos: QPointF):
        r = QRectF(self.rect())
        s = clamp01((pos.x() - r.left()) / max(1.0, r.width()))
        v = clamp01(1.0 - (pos.y() - r.top()) / max(1.0, r.height()))
        self._s, self._v = s, v
        self.update()
        self.changed.emit(s, v)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            self._pick(e.position())
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag:
            self._pick(e.position())
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = False
        super().mouseReleaseEvent(e)


class ClassicPicker(_HsvPicker):
    """SV rectangle with hue and brightness sliders beneath it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        self._plane = _SVPlane()
        self._plane.changed.connect(self._on_plane)
        v.addWidget(self._plane, 1)

        self._hue = _Slider()
        self._hue.set_stops([(i / 6.0, QColor.fromHsvF(i / 6.0, 1, 1))
                             for i in range(7)])
        self._hue.value_changed.connect(self._on_hue)
        v.addWidget(self._hue)

        self._bright = _Slider()
        self._bright.value_changed.connect(self._on_bright)
        v.addWidget(self._bright)

        self._refresh_children()

    def _refresh_children(self):
        self._plane.set_hsv(self._h, self._s, self._v)
        self._hue.set_value(self._h)
        self._bright.set_value(self._v)
        # Brightness ramp is shown for the current hue/saturation.
        self._bright.set_stops([(0.0, QColor("#000000")),
                                (1.0, QColor.fromHsvF(self._h, self._s, 1.0))])

    def set_color(self, c: QColor):
        super().set_color(c)
        self._refresh_children()

    def _on_plane(self, s: float, v: float):
        self._s, self._v = s, v
        self._refresh_children()
        self._emit()

    def _on_hue(self, h: float):
        self._h = h
        self._refresh_children()
        self._emit()

    def _on_bright(self, v: float):
        self._v = v
        self._refresh_children()
        self._emit()


# ── Mode 3: Value — HSB + RGB sliders with numeric readouts ──────────────────

class ValuePicker(_HsvPicker):
    """Six labelled sliders (H, S, B, R, G, B) with live numeric readouts.

    HSV is authoritative. RGB rows drive the colour by converting back through
    `QColor`, so the two groups always agree.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 2, 0, 2)
        v.setSpacing(7)

        self._rows: dict[str, tuple[_Slider, QLabel]] = {}
        for key, label in (("H", "H"), ("S", "S"), ("V", "B")):
            v.addLayout(self._make_row(key, label))
        sep = QWidget()
        sep.setFixedHeight(4)
        sep.setStyleSheet("background: transparent;")
        v.addWidget(sep)
        for key in ("R", "G", "B"):
            v.addLayout(self._make_row(key, key))
        v.addStretch()
        self._refresh_children()

    def _make_row(self, key: str, label: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setFixedWidth(10)
        lbl.setStyleSheet("color: #a8a29e; font-size: 11px; background: transparent;")
        row.addWidget(lbl)

        slider = _Slider()
        slider.value_changed.connect(lambda val, k=key: self._on_slider(k, val))
        row.addWidget(slider, 1)

        read = QLabel("")
        read.setFixedWidth(40)
        read.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        read.setStyleSheet("color: #e7e5e4; font-size: 11px; background: transparent;")
        row.addWidget(read)

        self._rows[key] = (slider, read)
        return row

    def set_color(self, c: QColor):
        super().set_color(c)
        self._refresh_children()

    def _refresh_children(self):
        c = self.color()
        r, g, b = c.red(), c.green(), c.blue()

        # Each slider previews what moving it would do, holding the others fixed.
        self._rows["H"][0].set_stops([(i / 6.0, QColor.fromHsvF(i / 6.0, 1, 1))
                                      for i in range(7)])
        self._rows["S"][0].set_stops([(0.0, QColor.fromHsvF(self._h, 0, self._v)),
                                      (1.0, QColor.fromHsvF(self._h, 1, self._v))])
        self._rows["V"][0].set_stops([(0.0, QColor("#000000")),
                                      (1.0, QColor.fromHsvF(self._h, self._s, 1.0))])
        self._rows["R"][0].set_stops([(0.0, QColor(0, g, b)), (1.0, QColor(255, g, b))])
        self._rows["G"][0].set_stops([(0.0, QColor(r, 0, b)), (1.0, QColor(r, 255, b))])
        self._rows["B"][0].set_stops([(0.0, QColor(r, g, 0)), (1.0, QColor(r, g, 255))])

        for key, val in (("H", self._h), ("S", self._s), ("V", self._v)):
            self._rows[key][0].set_value(val)
        for key, val in (("R", r / 255), ("G", g / 255), ("B", b / 255)):
            self._rows[key][0].set_value(val)

        self._rows["H"][1].setText(f"{round(self._h * 360)}°")
        self._rows["S"][1].setText(f"{round(self._s * 100)}%")
        self._rows["V"][1].setText(f"{round(self._v * 100)}%")
        for key, val in (("R", r), ("G", g), ("B", b)):
            self._rows[key][1].setText(str(val))

    def _on_slider(self, key: str, val: float):
        if key in ("H", "S", "V"):
            if key == "H":
                self._h = val
            elif key == "S":
                self._s = val
            else:
                self._v = val
        else:
            # RGB edit: rebuild the colour, then read HSV back so both agree.
            c = self.color()
            r, g, b = c.red(), c.green(), c.blue()
            byte = round(val * 255)
            if key == "R":
                r = byte
            elif key == "G":
                g = byte
            else:
                b = byte
            h, s, v, _ = QColor(r, g, b).getHsvF()
            self._h = self._h if h < 0 else h
            self._s, self._v = clamp01(s), clamp01(v)
        self._refresh_children()
        self._emit()
