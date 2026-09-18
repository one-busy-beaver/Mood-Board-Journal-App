"""In-app confirmation dialog (never an OS message box).

Used for the two destructive moments in the app: closing a journal with unsaved
changes, and deleting something from the explorer. Buttons are supplied by the
caller so the same overlay serves Save/Discard/Cancel and Delete/Cancel.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from views.base_overlay import BaseOverlay
from utils.shortcuts import ShortcutMap


class ConfirmOverlay(BaseOverlay):
    """`buttons` is a list of (label, style, callback) where style is one of
    'primary' | 'danger' | 'ghost'. Escape / click-outside cancels without
    running any callback."""

    CARD_W = 420
    CARD_H = 180

    STYLES = {
        "primary": ("#f59e0b", "#d97706", "white"),
        "danger":  ("#dc2626", "#b91c1c", "white"),
        "ghost":   ("#44403c", "#57534e", "#d6d3d1"),
    }

    def __init__(self, parent, shortcuts: ShortcutMap, title: str, message: str,
                 buttons: list[tuple[str, str, object]]):
        self._title = title
        self._message = message
        self._buttons = buttons
        super().__init__(parent, shortcuts)

    def _card_background(self) -> str:
        return "#292524"

    def _populate_card(self, layout: QVBoxLayout):
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(24, 22, 24, 18)
        v.setSpacing(10)

        title = QLabel(self._title)
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        title.setStyleSheet("color: #fafaf9; background: transparent;")
        v.addWidget(title)

        msg = QLabel(self._message)
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #a8a29e; font-size: 12px; background: transparent;")
        v.addWidget(msg)
        v.addStretch()

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        for label, style, callback in self._buttons:
            row.addWidget(self._make_button(label, style, callback))
        v.addLayout(row)

        layout.addWidget(wrap)

    def _make_button(self, label: str, style: str, callback) -> QPushButton:
        bg, hover, fg = self.STYLES.get(style, self.STYLES["ghost"])
        b = QPushButton(label)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedSize(104, 32)
        b.setStyleSheet(f"""
            QPushButton {{ background: {bg}; color: {fg}; border: none;
                           border-radius: 6px; font-size: 12px; font-weight: 600; }}
            QPushButton:hover {{ background: {hover}; }}
        """)

        def run():
            self._close()
            if callback is not None:
                callback()

        b.clicked.connect(run)
        return b
