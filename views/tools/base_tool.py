"""
Modular toolbar tool.

A Tool builds its own toolbar control and knows how to refresh itself when app
state changes. The default control is an icon button that runs `activate()`
(used by `ColorTool`); tools that need a richer control (e.g. a stepper) override
`create_control` / `refresh`. New tools subclass Tool and are added to
MainWindow's tool list.
"""

import os

from PyQt6.QtWidgets import QPushButton, QWidget
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon

_ICONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets", "icons",
)


def icon_path(filename: str) -> str:
    return os.path.join(_ICONS_DIR, filename)


class Tool:
    name: str = ""           # caption shown under the control
    tooltip: str = ""        # hover text
    icon_file: str | None = None  # filename in assets/icons/, or None

    def __init__(self):
        self._button: QPushButton | None = None

    def icon(self) -> QIcon:
        if not self.icon_file:
            return QIcon()
        return QIcon(icon_path(self.icon_file))

    # ── Toolbar integration ───────────────────────────────────────────────────

    def create_control(self, window) -> QWidget:
        """Build and return the tool's toolbar widget. Default: an icon button
        that runs `activate()`. Override for a custom control. Sizes follow the
        global UI scale (`window.ui_scale()`)."""
        s = window.ui_scale()
        b = QPushButton()
        b.setIcon(self.icon())
        b.setIconSize(QSize(round(22 * s), round(22 * s)))
        b.setFixedSize(round(34 * s), round(30 * s))
        b.setToolTip(self.tooltip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self.is_enabled(window) and self.activate(window))
        self._button = b
        return b

    def refresh(self, window) -> None:
        """Re-evaluate enabled state / dynamic styling. Override to update a
        custom control."""
        if self._button is not None:
            self._button.setEnabled(self.is_enabled(window))
            self.style_button(self._button, window)

    # ── Button-tool hooks (used by the default control) ───────────────────────

    def is_enabled(self, window) -> bool:
        return True

    def style_button(self, button, window) -> None:
        pass

    def activate(self, window) -> None:
        raise NotImplementedError
