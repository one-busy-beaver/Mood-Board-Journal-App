"""
Anchored in-app panel (popover).

Like `BaseOverlay` it is a child widget of the main window — never an OS popup —
but it does NOT dim or freeze the board. It anchors under a toolbar control
(GoodNotes / Notability style), and closes on Escape or a click anywhere outside
its card.

Subclasses implement `_populate_card(layout)`; optionally `_card_background()`,
`_initial_focus()`, `_on_close()`.
"""

from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt6.QtGui import QColor, QShortcut

from utils.shortcuts import ShortcutMap, DISMISS


class BasePanel(QWidget):
    closed = pyqtSignal()

    CARD_W = 300
    CARD_H = 420
    GAP = 8            # space between the anchor widget and the card
    EDGE_PAD = 10      # keep the card this far inside the window edges
    CARD_SHADOW = True # set False if the card has children that move/animate

    def __init__(self, parent: QWidget, shortcuts: ShortcutMap, anchor: QWidget | None = None):
        super().__init__(parent)
        self._shortcuts = shortcuts
        self._anchor = anchor
        self._closing = False

        # Transparent hit-catcher covering the window: clicks outside the card
        # dismiss the panel, but the board underneath stays fully visible.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
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

    # ── Card ──────────────────────────────────────────────────────────────────

    def _build_card(self):
        self._card = QFrame(self)
        self._card.setObjectName("panelCard")
        self._card.setFixedSize(self.CARD_W, self.CARD_H)
        self._card.setStyleSheet(f"""
            QFrame#panelCard {{
                background: {self._card_background()};
                border: 1px solid rgba(0, 0, 0, 0.25);
                border-radius: 10px;
            }}
        """)

        # QGraphicsDropShadowEffect caches its rendering and does not reliably
        # invalidate when *child* widgets move, which smears dragged children and
        # can fault on Windows. Panels with moving children opt out.
        if self.CARD_SHADOW:
            shadow = QGraphicsDropShadowEffect(self._card)
            shadow.setBlurRadius(28)
            shadow.setOffset(0, 6)
            shadow.setColor(QColor(0, 0, 0, 120))
            self._card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._populate_card(layout)
        self._reposition_card()
        self._card.show()

    def _reposition_card(self):
        """Place the card just below the anchor widget, clamped to the window."""
        if not hasattr(self, "_card"):
            return
        if self._anchor is not None and self._anchor.parentWidget() is not None:
            top_left = self._anchor.mapTo(self, QPoint(0, self._anchor.height()))
            x = top_left.x()
            y = top_left.y() + self.GAP
        else:
            x, y = self.EDGE_PAD, self.EDGE_PAD

        x = max(self.EDGE_PAD, min(x, self.width() - self.CARD_W - self.EDGE_PAD))
        y = max(self.EDGE_PAD, min(y, self.height() - self.CARD_H - self.EDGE_PAD))
        self._card.move(int(x), int(y))

    # ── Qt overrides ──────────────────────────────────────────────────────────

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reposition_card()

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
