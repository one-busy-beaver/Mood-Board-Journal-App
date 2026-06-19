from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QGraphicsDropShadowEffect
from PyQt6.QtCore import pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor, QShortcut

from utils.shortcuts import ShortcutMap, DISMISS


class BaseOverlay(QWidget):
    """Full-screen dimmed overlay with a centered card.
    Subclasses implement _populate_card, _card_background, _initial_focus, _on_close."""
    closed = pyqtSignal()

    CARD_W = 640
    CARD_H = 520

    def __init__(self, parent: QWidget, shortcuts: ShortcutMap):
        super().__init__(parent)
        self._shortcuts = shortcuts
        self._closing = False
        self._bg = parent.grab()
        self.setGeometry(parent.rect())
        self.raise_()
        self.show()
        self._build_card()
        QTimer.singleShot(0, self._initial_focus)
        QShortcut(shortcuts.key_sequence(DISMISS), self).activated.connect(self._close)

    # ── Subclass hooks ────────────────────────────────────────────────────────

    def _populate_card(self, layout: QVBoxLayout):
        raise NotImplementedError

    def _card_background(self) -> str:
        return "#fafaf9"

    def _initial_focus(self):
        pass

    def _on_close(self):
        pass

    # ── Card construction ─────────────────────────────────────────────────────

    def _build_card(self):
        self._card = QFrame(self)
        self._card.setObjectName("overlayCard")
        self._card.setFixedSize(self.CARD_W, self.CARD_H)
        self._card.setStyleSheet(f"""
            QFrame#overlayCard {{
                background: {self._card_background()};
                border-radius: 10px;
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 100))
        self._card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._populate_card(layout)
        self._reposition_card()
        self._card.show()

    def _reposition_card(self):
        if not hasattr(self, '_card'):
            return
        x = (self.width()  - self.CARD_W) // 2
        y = (self.height() - self.CARD_H) // 2
        self._card.move(x, y)

    # ── Qt overrides ──────────────────────────────────────────────────────────

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reposition_card()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._bg)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

    def mousePressEvent(self, e):
        if not self._card.geometry().contains(e.pos()):
            self._close()
        else:
            super().mousePressEvent(e)

    # ── Close ─────────────────────────────────────────────────────────────────

    def _close(self):
        if self._closing:
            return
        self._closing = True
        self._on_close()
        self.closed.emit()
        self.hide()
        self.deleteLater()
