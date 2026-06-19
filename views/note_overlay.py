from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor, QFont, QKeySequence, QShortcut

from models.note import Note
from controllers.board_controller import BoardController
from views.templates.plain_text import PlainTextTemplate


class NoteOverlay(QWidget):
    closed = pyqtSignal()

    CARD_W = 640
    CARD_H = 520
    TITLE_H = 44

    def __init__(self, note: Note, board_ctrl: BoardController, parent: QWidget):
        super().__init__(parent)
        self._note = note
        self._board_ctrl = board_ctrl
        self._closing = False

        # Snapshot the board BEFORE the overlay appears so paintEvent can show it dimmed
        self._bg = parent.grab()

        self.setGeometry(parent.rect())
        self.raise_()
        self.show()

        self._build_card()
        QTimer.singleShot(0, self._editor.setFocus)

        QShortcut(QKeySequence("Escape"), self).activated.connect(self._close)
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self._close)

    # ── Card construction ─────────────────────────────────────────────────────

    def _build_card(self):
        base = QColor(self._note.color)

        def blended(alpha: int) -> str:
            f = alpha / 255
            return QColor(
                int(base.red()   * (1 - f)),
                int(base.green() * (1 - f)),
                int(base.blue()  * (1 - f)),
            ).name()

        self._card = QFrame(self)
        self._card.setObjectName("noteCard")
        self._card.setFixedSize(self.CARD_W, self.CARD_H)
        self._card.setStyleSheet(f"""
            QFrame#noteCard {{
                background: {self._note.color};
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

        # ── Title bar ──
        title_bar = QWidget()
        title_bar.setFixedHeight(self.TITLE_H)
        title_bar.setStyleSheet(f"""
            QWidget {{
                background: {blended(18)};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
        """)
        tl = QHBoxLayout(title_bar)
        tl.setContentsMargins(16, 0, 10, 0)

        self._title_edit = QLineEdit(self._note.title)
        self._title_edit.setPlaceholderText("Untitled")
        self._title_edit.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        self._title_edit.setStyleSheet(
            "border: none; background: transparent; color: #44403c;"
        )
        tl.addWidget(self._title_edit)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(26, 26)
        close_btn.setFlat(True)
        close_btn.setStyleSheet("""
            QPushButton { color: #78716c; font-size: 20px; font-weight: bold;
                          background: transparent; border: none; padding: 0; }
            QPushButton:hover { color: #1c1917; }
        """)
        close_btn.clicked.connect(self._close)
        tl.addWidget(close_btn)
        layout.addWidget(title_bar)

        # ── Divider ──
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {blended(30)}; border: none;")
        layout.addWidget(div)

        # ── Editor ──
        editor_wrap = QWidget()
        editor_wrap.setStyleSheet("background: transparent;")
        ew = QVBoxLayout(editor_wrap)
        ew.setContentsMargins(12, 10, 12, 10)

        self._editor = PlainTextTemplate(self._note.content, compact=False)
        self._editor.setFont(QFont("Georgia", 12))
        self._editor.setStyleSheet("""
            QTextEdit {
                background: transparent; border: none;
                color: #1c1917;
                selection-background-color: #fde68a;
                padding: 4px;
            }
            QScrollBar:vertical { width: 6px; background: transparent; }
            QScrollBar::handle:vertical { background: #d6d3d1; border-radius: 3px; }
        """)
        ew.addWidget(self._editor)
        layout.addWidget(editor_wrap, stretch=1)

        # ── Footer ──
        footer = QWidget()
        footer.setStyleSheet("background: transparent;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 8, 16, 16)
        fl.addStretch()

        done_btn = QPushButton("Done")
        done_btn.setFixedSize(100, 32)
        done_btn.setStyleSheet("""
            QPushButton { background: #f59e0b; color: white; border: none;
                          border-radius: 6px; font-size: 12px; font-weight: 600; }
            QPushButton:hover { background: #d97706; }
            QPushButton:pressed { background: #b45309; }
        """)
        done_btn.clicked.connect(self._close)
        fl.addWidget(done_btn)
        layout.addWidget(footer)

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
        # Draw the frozen board snapshot so the background is visible behind the dim
        painter.drawPixmap(self.rect(), self._bg)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

    def mousePressEvent(self, e):
        if not self._card.geometry().contains(e.pos()):
            self._close()
        else:
            super().mousePressEvent(e)

    # ── Save & close ──────────────────────────────────────────────────────────

    def _close(self):
        if self._closing:
            return
        self._closing = True
        self._board_ctrl.update_title(self._note.id, self._title_edit.text())
        self._board_ctrl.update_content(self._note.id, self._editor.dump())
        self.closed.emit()
        self.hide()
        self.deleteLater()
