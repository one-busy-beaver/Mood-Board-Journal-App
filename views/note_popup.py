from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from models.note import Note
from controllers.board_controller import BoardController
from views.templates.plain_text import PlainTextTemplate


class NotePopup(QDialog):
    def __init__(self, note: Note, board_ctrl: BoardController, parent=None):
        super().__init__(parent)
        self._note = note
        self._board_ctrl = board_ctrl

        self.setWindowTitle(note.title or "Note")
        self.setMinimumSize(520, 420)
        self.resize(620, 500)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._build_ui()
        self._apply_styles()

        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self.accept)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self.reject)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(0)

        # Title row
        self._title_edit = QLineEdit(self._note.title)
        self._title_edit.setPlaceholderText("Untitled")
        self._title_edit.setFont(QFont("Segoe UI", 15, QFont.Weight.DemiBold))
        layout.addWidget(self._title_edit)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        layout.addSpacing(10)
        layout.addWidget(line)
        layout.addSpacing(10)

        # Body
        self._editor = PlainTextTemplate(self._note.content, compact=False)
        self._editor.setFont(QFont("Georgia", 12))
        layout.addWidget(self._editor, stretch=1)

        layout.addSpacing(12)

        # Footer buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._done_btn = QPushButton("Done")
        self._done_btn.setFixedSize(100, 32)
        self._done_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._done_btn)

        layout.addLayout(btn_row)

    def accept(self):
        self._save()
        super().accept()

    def reject(self):
        self._save()
        super().reject()

    def closeEvent(self, e):
        self._save()
        super().closeEvent(e)

    def _save(self):
        self._board_ctrl.update_title(self._note.id, self._title_edit.text())
        self._board_ctrl.update_content(self._note.id, self._editor.dump())

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #fafaf9;
            }
            QLineEdit {
                border: none;
                background: transparent;
                color: #1c1917;
                padding: 2px 0;
            }
            QLineEdit:focus {
                outline: none;
            }
            QFrame[frameShape="4"] {
                color: #e7e5e4;
            }
            QTextEdit {
                border: none;
                background: transparent;
                color: #292524;
            }
            QPushButton {
                background: #f59e0b;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #d97706;
            }
            QPushButton:pressed {
                background: #b45309;
            }
        """)
