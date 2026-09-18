from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QFont, QShortcut

from models.note import Note
from controllers.board_controller import BoardController
from utils.shortcuts import ShortcutMap, OVERLAY_CONFIRM
from views.base_overlay import BaseOverlay
from views.templates.plain_text import PlainTextTemplate
from utils.contrast import ink, muted_ink, shade, INK_DARK

# Highlight colour for selected text; dark ink is forced on top of it so the
# selection stays legible even on a dark note.
SELECTION = "#fde68a"
# Same amber the explorer and tab bar use for an unsaved marker.
ACCENT = "#f59e0b"


class NoteOverlay(BaseOverlay):
    """Zoomed note editor.

    There is no Done button: **Ctrl+S commits** the draft to the note, and the
    close glyph doubles as the unsaved indicator — a dot while dirty, exactly
    like a dirty journal tab. Closing while dirty asks before discarding.
    """

    CARD_W = 640
    CARD_H = 520
    TITLE_H = 44

    def __init__(self, note: Note, board_ctrl: BoardController,
                 parent, shortcuts: ShortcutMap):
        self._note = note
        self._board_ctrl = board_ctrl
        self._dirty = False
        self._hovering_close = False
        self._confirming_close = False
        # MainWindow sets this so the nested "unsaved changes" dialog is tracked
        # as the active overlay while it is up.
        self.dialog_opened = None
        super().__init__(parent, shortcuts)
        # NOTE: no QShortcut for Ctrl+S here. MainWindow owns a window-scoped
        # Ctrl+S, and a window-scoped shortcut always beats anything inside an
        # overlay — two of them for the same key are *ambiguous*, so Qt fires
        # NEITHER and Ctrl+S silently did nothing. MainWindow._save() therefore
        # forwards to `self._save()` while an overlay is open. Ctrl+Return is
        # ours alone, so a plain shortcut is fine.
        QShortcut(shortcuts.key_sequence(OVERLAY_CONFIRM), self).activated.connect(
            self._confirm)

    # ── BaseOverlay hooks ─────────────────────────────────────────────────────

    def _card_background(self) -> str:
        return self._note.color

    def _populate_card(self, layout: QVBoxLayout):
        # Every colour here is derived from the note's own colour, so the chrome
        # stays readable on a pale cream note and on a saturated or dark one.
        # `shade` tints toward black on light notes and toward white on dark
        # ones; `ink`/`muted_ink` pick the text colour by WCAG luminance.
        bg = self._note.color
        self._text_ink = text_ink = ink(bg)
        self._chrome_ink = chrome_ink = muted_ink(bg)
        bar_bg = shade(bg, 0.07)
        divider = shade(bg, 0.14)

        # ── Title bar ──
        title_bar = QWidget()
        title_bar.setFixedHeight(self.TITLE_H)
        title_bar.setStyleSheet(f"""
            QWidget {{
                background: {bar_bg};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
        """)
        tl = QHBoxLayout(title_bar)
        tl.setContentsMargins(16, 0, 10, 0)

        hint = QLabel("Note")
        hint.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        hint.setStyleSheet(
            f"border: none; background: transparent; color: {chrome_ink};")
        tl.addWidget(hint)
        tl.addStretch()

        # The close button doubles as the unsaved-changes indicator: a dot while
        # the draft is dirty, reverting to × on hover so it still reads as close.
        self._close_btn = QPushButton("×")
        self._close_btn.setFixedSize(26, 26)
        self._close_btn.setFlat(True)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self._close)
        self._close_btn.installEventFilter(self)
        tl.addWidget(self._close_btn)
        self._refresh_close_button()
        layout.addWidget(title_bar)

        # ── Divider ──
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {divider}; border: none;")
        layout.addWidget(div)

        # ── Editor ──
        editor_wrap = QWidget()
        editor_wrap.setStyleSheet("background: transparent;")
        ew = QVBoxLayout(editor_wrap)
        ew.setContentsMargins(12, 10, 12, 14)

        self._editor = PlainTextTemplate(self._note.content, compact=False)
        self._editor.setFont(QFont("Georgia", self._note.font_size))
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background: transparent; border: none;
                color: {text_ink};
                selection-background-color: {SELECTION};
                selection-color: {INK_DARK};
                padding: 4px;
            }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {chrome_ink};
                                           border-radius: 3px; }}
        """)
        ew.addWidget(self._editor)
        layout.addWidget(editor_wrap, stretch=1)

        # Typing marks the draft dirty, which turns the close glyph into a dot.
        self._editor.textChanged.connect(self._on_text_changed)

    def _initial_focus(self):
        self._editor.setFocus()

    # ── Dirty state ──────────────────────────────────────────────────────────

    def _on_text_changed(self):
        if not self._dirty:
            self._dirty = True
            self._refresh_close_button()

    def _refresh_close_button(self):
        """Show a dot while there are unsaved edits, matching the explorer and
        tab bar. Hovering reveals the × so closing stays obviously available."""
        btn = getattr(self, "_close_btn", None)
        if btn is None:
            return
        show_dot = self._dirty and not self._hovering_close
        btn.setText("●" if show_dot else "×")
        btn.setStyleSheet(f"""
            QPushButton {{ color: {ACCENT if show_dot else self._chrome_ink};
                           font-size: {13 if show_dot else 20}px;
                           font-weight: bold; background: transparent;
                           border: none; padding: 0; }}
            QPushButton:hover {{ color: {self._text_ink}; }}
        """)
        btn.setToolTip("Unsaved changes — Ctrl+S to save" if self._dirty
                       else "Close")

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_close_btn", None):
            if event.type() == QEvent.Type.Enter:
                self._hovering_close = True
                self._refresh_close_button()
            elif event.type() == QEvent.Type.Leave:
                self._hovering_close = False
                self._refresh_close_button()
        return super().eventFilter(obj, event)

    # ── Saving ───────────────────────────────────────────────────────────────

    def _save(self):
        """Ctrl+S: commit the draft to the note.

        This updates the in-memory model only; the journal itself is still
        written to disk by its own explicit save, as everywhere else in the app.
        """
        self._board_ctrl.update_content(self._note.id, self._editor.dump())
        self._dirty = False
        self._refresh_close_button()

    def _confirm(self):
        """Ctrl+Return: commit and close."""
        self._save()
        self._close()

    def _close(self):
        """Closing with unsaved edits asks first, the way a dirty journal tab
        does — a draft is never silently discarded."""
        if self._dirty and not self._confirming_close:
            self._confirming_close = True
            self._prompt_unsaved()
            return
        super()._close()

    def _prompt_unsaved(self):
        from views.confirm_overlay import ConfirmOverlay

        def save_and_close():
            self._save()
            self._close()

        def discard():
            self._dirty = False
            self._close()

        dialog = ConfirmOverlay(
            self.parentWidget(), self._shortcuts,
            "Save changes to this note?",
            "Your edits will be lost if you close without saving.",
            [
                ("Save", "primary", save_and_close),
                ("Don't Save", "danger", discard),
                ("Cancel", "ghost", None),
            ],
        )
        # Dismissing the dialog (Escape / click-outside / Cancel) just returns to
        # editing, so clear the guard once it is gone.
        dialog.closed.connect(self._end_close_confirmation)
        if self.dialog_opened is not None:
            self.dialog_opened(dialog)

    def _end_close_confirmation(self):
        self._confirming_close = False
