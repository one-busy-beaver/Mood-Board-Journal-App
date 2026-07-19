"""Font-size tool: a −/value/+ stepper that adjusts the *selected note's* body
font size (a per-note property). Distinct from Ctrl -/= which is the global
"resolution" scale applied on top of every note's font size."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt

from views.tools.base_tool import Tool


class FontSizeTool(Tool):
    name = "Font"
    tooltip = "font size of the selected note"
    STEP = 1

    def create_control(self, window) -> QWidget:
        s = window.ui_scale()
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self._minus = self._step_btn("−", "left", s)
        self._minus.clicked.connect(lambda: window.change_active_font(-self.STEP))
        h.addWidget(self._minus)

        self._value = QLabel("–")
        self._value.setFixedSize(round(30 * s), round(26 * s))
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value.setStyleSheet(f"""
            QLabel {{ color: #e7e5e4; background: #38332f;
                      border-top: 1px solid #57534e; border-bottom: 1px solid #57534e;
                      font-size: {round(12 * s)}px; }}
        """)
        h.addWidget(self._value)

        self._plus = self._step_btn("+", "right", s)
        self._plus.clicked.connect(lambda: window.change_active_font(+self.STEP))
        h.addWidget(self._plus)

        return wrap

    def refresh(self, window) -> None:
        note = window.active_note()
        enabled = note is not None
        self._minus.setEnabled(enabled)
        self._plus.setEnabled(enabled)
        self._value.setText(str(note.font_size) if note else "–")

    @staticmethod
    def _step_btn(glyph: str, side: str, s: float) -> QPushButton:
        b = QPushButton(glyph)
        b.setFixedSize(round(24 * s), round(26 * s))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        r = round(5 * s)
        radius = (f"border-top-left-radius:{r}px;border-bottom-left-radius:{r}px;"
                  if side == "left" else
                  f"border-top-right-radius:{r}px;border-bottom-right-radius:{r}px;")
        b.setStyleSheet(f"""
            QPushButton {{ color: #d6d3d1; background: #44403c; border: 1px solid #57534e;
                           font-size: {round(15 * s)}px; font-weight: 600; {radius} }}
            QPushButton:hover:enabled {{ background: #57534e; color: #fafaf9; }}
            QPushButton:disabled {{ color: #57534e; }}
        """)
        return b
