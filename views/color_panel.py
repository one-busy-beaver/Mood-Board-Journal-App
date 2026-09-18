"""
Colour panel — one page, Colors-app style.

Layout (top to bottom):

    [ Disc | Classic | Value ]      mode bar — swaps only the picker surface
    (the picker for the active mode)
    preview + hex field
    ─────────────────────────────
    saved swatches                  always visible, shared by every journal
    [ ＋ Save ]        [ Apply ]

There is no separate "Saved" page: the palette sits under the picker so a saved
colour is one click away while you are choosing. The palette is global (see
`SettingsController`), so colours saved in one journal appear in all of them.

Applies live to the active note (preview-driven): `_set_draft` previews,
`_apply_current` commits, and closing without Apply restores `_original_color`.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QLineEdit, QFrame,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor

from controllers.board_controller import BoardController
from controllers.settings_controller import SettingsController
from utils.shortcuts import ShortcutMap
from views.base_panel import BasePanel
from views.widgets.color_pickers import DiscPicker, ClassicPicker, ValuePicker
from views.widgets.swatch_grid import SwatchGrid


class ColorPanel(BasePanel):
    # Emitted when the user commits a colour with Apply. MainWindow decides what
    # the current target is, so this can later drive objects other than notes.
    color_applied = pyqtSignal(str)

    CARD_W = 300
    CARD_H = 528
    # Swatches are dragged/animated inside this card; a drop-shadow effect over
    # moving children smears and can crash on Windows.
    CARD_SHADOW = False

    MODES = ("Disc", "Classic", "Value")

    def __init__(self, note_id: str, current_color: str,
                 board_ctrl: BoardController, settings_ctrl: SettingsController,
                 parent, shortcuts: ShortcutMap, anchor: QWidget | None = None):
        self._note_id = note_id
        self._color = QColor(current_color)
        # Baseline to restore if the panel closes without Apply.
        self._original_color = QColor(current_color)
        self._board_ctrl = board_ctrl
        self._settings = settings_ctrl
        self._syncing = False
        super().__init__(parent, shortcuts, anchor)

    # ── BasePanel hooks ───────────────────────────────────────────────────────

    def _card_background(self) -> str:
        return "#2b2724"

    def _populate_card(self, layout: QVBoxLayout):
        layout.addWidget(self._build_header())

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        v = QVBoxLayout(body)
        v.setContentsMargins(14, 10, 14, 12)
        v.setSpacing(10)

        v.addWidget(self._build_mode_bar())
        v.addWidget(self._build_pickers(), 1)
        v.addLayout(self._build_preview_row())
        v.addWidget(self._divider())
        v.addWidget(self._build_saved_strip())
        v.addLayout(self._build_actions())

        layout.addWidget(body, 1)

        self._select_mode(0)
        self._sync_from_color()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(34)
        bar.setStyleSheet("background: #221f1d; border-top-left-radius: 9px;"
                          "border-top-right-radius: 9px;")
        h = QHBoxLayout(bar)
        h.setContentsMargins(14, 0, 6, 0)

        title = QLabel("Colors")
        title.setStyleSheet("color: #fafaf9; font-size: 13px; font-weight: 600;"
                            "background: transparent;")
        h.addWidget(title)
        h.addStretch()

        close = QPushButton("✕")
        close.setFixedSize(24, 24)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet("""
            QPushButton { color: #a8a29e; background: transparent; border: none;
                          font-size: 14px; }
            QPushButton:hover { color: #fafaf9; }
        """)
        close.clicked.connect(self._close)
        h.addWidget(close)
        return bar

    # ── Mode bar ──────────────────────────────────────────────────────────────

    def _build_mode_bar(self) -> QWidget:
        wrap = QWidget()
        wrap.setFixedHeight(28)
        wrap.setStyleSheet("background: #221f1d; border-radius: 6px;")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(3)

        self._mode_btns: list[QPushButton] = []
        for i, name in enumerate(self.MODES):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton { color: #a8a29e; background: transparent; border: none;
                              border-radius: 4px; font-size: 11px; }
                QPushButton:hover { color: #e7e5e4; }
                QPushButton:checked { color: #fafaf9; background: #3a3330;
                                      font-weight: 600; }
            """)
            b.clicked.connect(lambda _=False, idx=i: self._select_mode(idx))
            self._mode_btns.append(b)
            h.addWidget(b, 1)
        return wrap

    def _build_pickers(self) -> QWidget:
        self._pickers = QStackedWidget()
        self._pickers.setStyleSheet("background: transparent;")
        # All modes share one height so swapping modes doesn't resize the card.
        self._pickers.setFixedHeight(232)
        self._disc = DiscPicker(208)
        self._classic = ClassicPicker()
        self._value = ValuePicker()
        for p in (self._disc, self._classic, self._value):
            p.color_changed.connect(self._on_picker)
            self._pickers.addWidget(p)
        return self._pickers

    def _select_mode(self, index: int):
        self._pickers.setCurrentIndex(index)
        for i, b in enumerate(self._mode_btns):
            b.setChecked(i == index)
        # Hand the current colour to the newly shown picker so all modes agree.
        self._syncing = True
        self._pickers.currentWidget().set_color(self._color)
        self._syncing = False

    # ── Preview + hex ─────────────────────────────────────────────────────────

    def _build_preview_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._preview = QFrame()
        self._preview.setFixedSize(46, 26)
        row.addWidget(self._preview)

        self._hex = QLineEdit()
        self._hex.setFixedHeight(26)
        self._hex.setStyleSheet("""
            QLineEdit { color: #e7e5e4; background: #38332f; border: 1px solid #57534e;
                        border-radius: 5px; padding: 0 8px; font-size: 12px; }
        """)
        self._hex.editingFinished.connect(self._on_hex)
        row.addWidget(self._hex, 1)
        return row

    @staticmethod
    def _divider() -> QWidget:
        d = QFrame()
        d.setFixedHeight(1)
        d.setStyleSheet("background: #3f3a36; border: none;")
        return d

    # ── Saved swatches (always visible, global palette) ───────────────────────

    def _build_saved_strip(self) -> QWidget:
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        self._saved_grid = SwatchGrid()
        self._saved_grid.picked.connect(lambda c: self._set_draft(QColor(c)))
        self._saved_grid.delete_requested.connect(self._remove_saved)
        self._saved_grid.reordered.connect(self._reorder_saved)
        self._saved_grid.rebuild_requested.connect(self._reload_saved)
        v.addWidget(self._saved_grid)

        self._saved_empty = QLabel("No saved colours yet — tap ＋ Save.")
        self._saved_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._saved_empty.setStyleSheet(
            "color: #78716c; font-size: 10px; background: transparent; padding: 6px;")
        v.addWidget(self._saved_empty)

        self._reload_saved()
        return wrap

    def _reload_saved(self):
        colors = list(self._settings.saved_colors)
        has = bool(colors)
        self._saved_empty.setVisible(not has)
        self._saved_grid.setVisible(has)
        self._saved_grid.set_colors(colors)

    def _remove_saved(self, color: str):
        self._settings.remove_saved_color(color)
        self._reload_saved()
        self._refresh_save_state()  # that colour can be saved again now

    def _reorder_saved(self, color: str, new_index: int):
        # The grid has already animated the chips into place; only sync the model
        # here — rebuilding would destroy the settle animation.
        self._settings.move_saved_color(color, new_index)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _build_actions(self) -> QHBoxLayout:
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self._save_btn = QPushButton("＋  Save")
        self._save_btn.setToolTip("Add this colour to your saved palette")
        self._style_action(self._save_btn, primary=False)
        self._save_btn.clicked.connect(self._save_current)
        actions.addWidget(self._save_btn)

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setToolTip("Apply this colour to the selected note")
        self._style_action(self._apply_btn, primary=True)
        self._apply_btn.clicked.connect(self._apply_current)
        actions.addWidget(self._apply_btn)
        return actions

    @staticmethod
    def _style_action(btn: QPushButton, primary: bool):
        btn.setFixedHeight(32)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            btn.setStyleSheet("""
                QPushButton { background: #f59e0b; color: #ffffff; border: none;
                              border-radius: 6px; font-size: 12px; font-weight: 600; }
                QPushButton:hover { background: #d97706; }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton { background: #44403c; color: #e7e5e4;
                              border: 1px solid #57534e; border-radius: 6px;
                              font-size: 12px; font-weight: 600; }
                QPushButton:hover:enabled { background: #57534e; color: #fafaf9; }
                QPushButton:disabled { background: #2f2b28; color: #6ee7b7;
                                       border: 1px solid #3f3a36; }
            """)

    def _flash(self, btn: QPushButton, text: str, ms: int = 900):
        """Briefly confirm an action on its own button.

        The button's true label is remembered the first time it is flashed, so
        flashing again while a previous flash is still showing cannot capture the
        confirmation text as the label to restore — which used to leave the
        button stuck on it permanently.
        """
        if not hasattr(self, "_flash_labels"):
            self._flash_labels: dict[QPushButton, str] = {}
            self._flash_timers: dict[QPushButton, QTimer] = {}
        if btn not in self._flash_labels:
            self._flash_labels[btn] = btn.text()

        existing = self._flash_timers.get(btn)
        if existing is not None:
            existing.stop()

        btn.setText(text)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda b=btn: self._restore_flash(b))
        timer.start(ms)
        self._flash_timers[btn] = timer

    def _restore_flash(self, btn: QPushButton):
        label = getattr(self, "_flash_labels", {}).get(btn)
        if label is None:
            return
        try:
            btn.setText(label)
        except RuntimeError:
            pass  # button destroyed with the panel
        self._flash_timers.pop(btn, None)

    # ── Colour flow ───────────────────────────────────────────────────────────

    def _set_draft(self, color: QColor):
        """Update the working (draft) colour and preview it on the target.

        This is NOT a commit: `_original_color` is restored if the panel closes
        without Apply. Only `_apply_current()` makes the change permanent.
        """
        if not color.isValid():
            return
        self._color = color
        self._preview_target(color.name())
        self._sync_from_color()

    def _preview_target(self, hex_color: str):
        """Paint the note live so the colour can be judged in context."""
        self._board_ctrl.update_color(self._note_id, hex_color)

    def _apply_current(self):
        """Commit the draft colour — this is what Apply does."""
        self._board_ctrl.update_color(self._note_id, self._color.name())
        self._original_color = QColor(self._color)   # new baseline; nothing to revert
        self.color_applied.emit(self._color.name())
        self._flash(self._apply_btn, "Applied ✓")

    def _on_close(self):
        # Dismissed without Apply → undo the live preview.
        if self._original_color.name() != self._board_ctrl_color():
            self._board_ctrl.update_color(self._note_id, self._original_color.name())

    def _board_ctrl_color(self) -> str:
        note = next((n for n in self._board_ctrl.board.notes
                     if n.id == self._note_id), None)
        return note.color if note else self._original_color.name()

    def _sync_from_color(self):
        """Push the current colour into every widget. Guarded by `_syncing` so
        the pickers' own change signals don't loop back."""
        self._syncing = True
        c = self._color
        self._pickers.currentWidget().set_color(c)
        self._preview.setStyleSheet(
            f"background: {c.name()}; border: 1px solid rgba(255,255,255,0.3);"
            "border-radius: 5px;"
        )
        self._hex.setText(c.name().upper())
        self._refresh_save_state()
        self._syncing = False

    def _is_saved(self, color: QColor | None = None) -> bool:
        return self._settings.is_saved((color or self._color).name())

    def _refresh_save_state(self):
        """The Save button tracks the CURRENT colour: already in the palette →
        'Saved ✓' and disabled; a new colour → an active '＋ Save'."""
        btn = getattr(self, "_save_btn", None)
        if btn is None:
            return
        saved = self._is_saved()
        # Keep _flash's remembered label in step with the button's real state.
        label = "Saved ✓" if saved else "＋  Save"
        if hasattr(self, "_flash_labels"):
            self._flash_labels[btn] = label
            timer = getattr(self, "_flash_timers", {}).get(btn)
            if timer is not None:
                timer.stop()
                self._flash_timers.pop(btn, None)
        btn.setText(label)
        btn.setEnabled(not saved)

    def _on_picker(self, c: QColor):
        if self._syncing:
            return
        self._set_draft(c)

    def _on_hex(self):
        if self._syncing:
            return
        text = self._hex.text().strip()
        if text and not text.startswith("#"):
            text = "#" + text
        c = QColor(text)
        if c.isValid():
            self._set_draft(c)
        else:
            self._sync_from_color()   # reject: restore the last good value

    def _save_current(self):
        """Save to the global palette only — does NOT change the note."""
        self._settings.save_color(self._color.name())
        self._reload_saved()
        # The button reflects palette membership, so it switches to a disabled
        # "Saved ✓" and back to "＋ Save" as soon as the colour changes.
        self._refresh_save_state()
