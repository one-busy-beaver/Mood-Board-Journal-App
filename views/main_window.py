from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QApplication, QTextEdit, QLineEdit,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut

from controllers.board_controller import BoardController
from controllers.persistence_controller import PersistenceController
from models.note import Note
from utils.shortcuts import ShortcutMap, SAVE, NEW_NOTE, DELETE, DELETE_ALT
from utils.shortcuts import REORDER_UP, REORDER_DOWN, REORDER_TO_FRONT, REORDER_TO_BACK
from utils.shortcuts import SCALE_UP, SCALE_DOWN, SCALE_RESET
from views.workspace import Workspace
from views.note_window import NoteWindow
from views.note_overlay import NoteOverlay
from views.color_picker_overlay import ColorPickerOverlay
from views.tools.base_tool import Tool
from views.tools.color_tool import ColorTool
from views.tools.font_size_tool import FontSizeTool


class MainWindow(QMainWindow):
    DEFAULT_NOTE_W = 240
    DEFAULT_NOTE_H = 200

    def __init__(self, board_ctrl: BoardController, persistence: PersistenceController,
                 shortcuts: ShortcutMap):
        super().__init__()
        self._board_ctrl = board_ctrl
        self._persistence = persistence
        self._shortcuts = shortcuts
        self._active_overlay: NoteOverlay | None = None
        self._active_note_id: str | None = None
        self._dirty = False

        # Registered toolbar tools (add new ones here)
        self._tools: list[Tool] = [ColorTool(), FontSizeTool()]

        self.setWindowTitle("Journal")
        self.resize(1280, 800)
        self._build_ui()
        self._wire_shortcuts()
        self._wire_controller()
        self._load_saved_notes()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet("QMainWindow { background: #1c1917; }")
        central = QWidget()
        self.setCentralWidget(central)
        self._root_layout = QVBoxLayout(central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        self._toolbar = self._build_toolbar()
        self._root_layout.addWidget(self._toolbar)

        self._workspace = Workspace(self._board_ctrl.board.scale)
        self._workspace.create_note_requested.connect(self._on_create_at)
        self._root_layout.addWidget(self._workspace)

    def ui_scale(self) -> float:
        """Global UI zoom ('resolution'): scales the panel and note box sizes,
        but NOT the body text (that's per-note font_size)."""
        return self._board_ctrl.board.scale

    def _px(self, base: float) -> int:
        return max(1, round(base * self.ui_scale()))

    def _rebuild_toolbar(self):
        old = self._toolbar
        self._toolbar = self._build_toolbar()
        self._root_layout.removeWidget(old)
        old.deleteLater()
        self._root_layout.insertWidget(0, self._toolbar)
        self._update_dirty_indicator()

    def _build_toolbar(self) -> QWidget:
        s = self.ui_scale()
        bar = QWidget()
        bar.setFixedHeight(self._px(58))
        bar.setStyleSheet(
            "background: #292524; border-bottom: 1px solid #3a3330;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(self._px(14), 0, self._px(14), 0)
        layout.setSpacing(self._px(6))
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self._make_brand("Journal"))
        layout.addWidget(self._make_divider())

        # ── Tools (control + name underneath) ──
        for tool in self._tools:
            layout.addWidget(self._make_tool(tool.create_control(self), tool.name))

        layout.addStretch()

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: #78716c; font-size: {self._px(11)}px;")
        layout.addWidget(self._status_label)
        layout.addSpacing(self._px(8))

        add_btn = self._make_btn("+ Note", "#f59e0b", "#d97706", w=self._px(76))
        add_btn.setToolTip("New note  (Ctrl+N)")
        add_btn.clicked.connect(self._add_note_center)
        layout.addWidget(add_btn)

        save_btn = self._make_btn("Save", "#44403c", "#57534e", w=self._px(58),
                                  text_color="#d6d3d1")
        save_btn.setToolTip("Save  (Ctrl+S)")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        self._refresh_tools()
        return bar

    def _make_divider(self) -> QWidget:
        div = QWidget()
        div.setFixedSize(1, self._px(34))
        div.setStyleSheet("background: #3a3330;")
        return div

    def _make_brand(self, text: str) -> QWidget:
        """Title styled with the same two-row geometry as a tool, so its baseline
        lines up with the tool icons rather than floating between icon and caption."""
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(self._px(2), 0, self._px(8), 0)
        v.setSpacing(self._px(3))
        label = QLabel(text)
        label.setFixedHeight(self._px(22))
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet(
            f"color: #f5f5f4; font-size: {self._px(15)}px; font-weight: 600; "
            "letter-spacing: 0.5px; background: transparent;"
        )
        v.addWidget(label)
        spacer = QLabel("")  # matches the tool caption row height for alignment
        spacer.setFixedHeight(self._px(11))
        spacer.setStyleSheet("background: transparent;")
        v.addWidget(spacer)
        return wrap

    def _make_tool(self, widget: QWidget, name: str) -> QWidget:
        """Wrap a tool control with a small caption underneath (toolbar pattern)."""
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(self._px(2), 0, self._px(2), 0)
        v.setSpacing(self._px(3))
        v.addWidget(widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        caption = QLabel(name)
        caption.setFixedHeight(self._px(11))
        caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        caption.setStyleSheet(
            f"color: #a8a29e; font-size: {self._px(9)}px; font-weight: 500; "
            "background: transparent;"
        )
        v.addWidget(caption)
        return wrap

    def _refresh_tools(self):
        """Re-evaluate each tool's enabled state / dynamic control."""
        for tool in self._tools:
            tool.refresh(self)

    def _make_btn(self, text: str, bg: str, hover: str, w: int = 72,
                  text_color: str = "white") -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(w, self._px(30))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {text_color};
                border: none;
                border-radius: {self._px(5)}px;
                font-size: {self._px(12)}px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:pressed {{ background: {hover}; }}
        """)
        return btn

    # ── Wiring ────────────────────────────────────────────────────────────────

    def _wire_shortcuts(self):
        sc = self._shortcuts

        def bind(action: str, slot):
            QShortcut(sc.key_sequence(action), self).activated.connect(slot)

        bind(SAVE,             self._save)
        bind(NEW_NOTE,         self._add_note_center)
        bind(DELETE,           self._delete_selected)
        bind(DELETE_ALT,       self._delete_selected)
        bind(REORDER_UP,       self._reorder_up)
        bind(REORDER_DOWN,     self._reorder_down)
        bind(REORDER_TO_FRONT, self._reorder_to_front)
        bind(REORDER_TO_BACK,  self._reorder_to_back)
        bind(SCALE_UP,         lambda: self._board_ctrl.nudge_scale(+1))
        bind(SCALE_DOWN,       lambda: self._board_ctrl.nudge_scale(-1))
        bind(SCALE_RESET,      self._board_ctrl.reset_scale)

    def _wire_controller(self):
        self._board_ctrl.note_added.connect(self._on_note_added)
        self._board_ctrl.note_removed.connect(self._on_note_removed)
        self._board_ctrl.z_order_changed.connect(self._on_z_changed)
        self._board_ctrl.note_color_changed.connect(self._on_note_color_changed)
        self._board_ctrl.note_font_changed.connect(self._on_note_font_changed)
        self._board_ctrl.scale_changed.connect(self._on_scale_changed)
        # Any model mutation marks the board dirty (persisted only on explicit Save)
        self._board_ctrl.board_changed.connect(self._on_board_changed)

    def _load_saved_notes(self):
        for note in self._board_ctrl.board.notes:
            self._on_note_added(note)
        self._workspace.restack()
        # Loading isn't a user edit — start clean
        self._dirty = False

    # ── Note lifecycle ────────────────────────────────────────────────────────

    def _on_note_added(self, note: Note):
        win = self._workspace.add_note(note)
        win.removed.connect(self._board_ctrl.remove_note)
        win.expand_requested.connect(self._open_overlay)
        win.geometry_changed.connect(self._on_geometry_changed)
        win.content_changed.connect(self._board_ctrl.update_content)
        win.bring_to_front_requested.connect(self._on_note_focused)

    def _on_note_removed(self, note_id: str):
        if self._active_note_id == note_id:
            self._active_note_id = None
            self._refresh_tools()
        self._workspace.remove_note(note_id)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _add_note_center(self):
        if self._active_overlay:
            return
        # Convert the on-screen center to base (unscaled) coords the model stores.
        s = self.ui_scale()
        c = self._workspace.rect().center()
        self._board_ctrl.create_note(
            c.x() / s - self.DEFAULT_NOTE_W / 2, c.y() / s - self.DEFAULT_NOTE_H / 2
        )

    def _on_create_at(self, x: float, y: float):
        s = self.ui_scale()
        x = max(0, x / s - self.DEFAULT_NOTE_W / 2)
        y = max(0, y / s - self.DEFAULT_NOTE_H / 2)
        self._board_ctrl.create_note(x, y)

    def _open_overlay(self, note_id: str):
        if self._active_overlay:
            return
        note = next(
            (n for n in self._board_ctrl.board.notes if n.id == note_id), None
        )
        if note is None:
            return
        overlay = NoteOverlay(note, self._board_ctrl, self, self._shortcuts)
        self._active_overlay = overlay
        overlay.closed.connect(lambda: self._on_overlay_closed(note_id))

    def _on_note_focused(self, note_id: str):
        self._active_note_id = note_id
        self._workspace.raise_note(note_id)  # visual raise; persistent z unchanged
        self._refresh_tools()

    def _on_overlay_closed(self, note_id: str):
        self._active_overlay = None
        win = self._workspace.window(note_id)
        if win:
            win.sync_from_model()

    def _on_note_color_changed(self, note_id: str, _color: str):
        win = self._workspace.window(note_id)
        if win:
            win.refresh_color()
        if note_id == self._active_note_id:
            self._refresh_tools()

    def _on_note_font_changed(self, note_id: str, _size: int):
        win = self._workspace.window(note_id)
        if win:
            win.apply_font()
        if note_id == self._active_note_id:
            self._refresh_tools()

    def _on_scale_changed(self, scale: float):
        self._workspace.apply_scale(scale)  # relayout note geometry (not body font)
        self._rebuild_toolbar()             # scale the panel/icons/buttons/words

    # ── Public interface used by Tools ────────────────────────────────────────

    def active_note(self) -> Note | None:
        if self._active_note_id is None:
            return None
        return next(
            (n for n in self._board_ctrl.board.notes if n.id == self._active_note_id),
            None,
        )

    def change_active_font(self, delta: int):
        note = self.active_note()
        if note is None:
            return
        self._board_ctrl.update_font_size(note.id, note.font_size + delta)

    def open_color_picker_for_active(self):
        if self._active_overlay:
            return
        note = self.active_note()
        if note is None:
            self._flash_status("Select a note first")
            return
        overlay = ColorPickerOverlay(
            note.id, note.color, self._board_ctrl, self, self._shortcuts
        )
        self._active_overlay = overlay
        overlay.closed.connect(lambda: setattr(self, '_active_overlay', None))

    def _on_z_changed(self, note_id: str, z: float):
        # z_index already updated in the model; re-apply persistent stacking order.
        self._workspace.restack()

    def _on_geometry_changed(self, note_id: str, x: float, y: float,
                              w: float, h: float):
        self._board_ctrl.update_geometry(note_id, x=x, y=y, width=w, height=h)

    def _delete_selected(self):
        if self._active_overlay or self._editing_text():
            return
        if self._active_note_id:
            self._board_ctrl.remove_note(self._active_note_id)

    # ── Z-order reordering ────────────────────────────────────────────────────

    @staticmethod
    def _editing_text() -> bool:
        """True while a text field has focus, so note-management shortcuts
        (delete, reorder) defer to normal text editing."""
        return isinstance(QApplication.focusWidget(), (QTextEdit, QLineEdit))

    def _reorder(self, action):
        if self._active_overlay or self._editing_text():
            return
        if self._active_note_id:
            action(self._active_note_id)

    def _reorder_up(self):
        self._reorder(self._board_ctrl.reorder_one_up)

    def _reorder_down(self):
        self._reorder(self._board_ctrl.reorder_one_down)

    def _reorder_to_front(self):
        self._reorder(self._board_ctrl.bring_to_front)

    def _reorder_to_back(self):
        self._reorder(self._board_ctrl.send_to_back)

    # ── Persistence (explicit save only — no autosave, no save-on-close) ──────

    def _on_board_changed(self):
        self._dirty = True
        self._update_dirty_indicator()

    def _save(self):
        self._persistence.save(self._board_ctrl.board)
        self._dirty = False
        self._status_label.setText("Saved ✓")
        self._status_label.setStyleSheet("color: #6ee7b7; font-size: 11px;")
        QTimer.singleShot(1500, self._update_dirty_indicator)

    def _update_dirty_indicator(self):
        if self._dirty:
            self._status_label.setText("● Unsaved")
            self._status_label.setStyleSheet("color: #f59e0b; font-size: 11px;")
        else:
            self._status_label.setText("")
            self._status_label.setStyleSheet("color: #78716c; font-size: 11px;")

    def _flash_status(self, msg: str, ms: int = 2000):
        self._status_label.setText(msg)
        self._status_label.setStyleSheet("color: #78716c; font-size: 11px;")
        QTimer.singleShot(ms, self._update_dirty_indicator)

    # ── Window events ─────────────────────────────────────────────────────────

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._active_overlay:
            self._active_overlay.setGeometry(self.rect())

    def closeEvent(self, e):
        # Deliberately does NOT persist — unsaved changes are discarded unless the
        # user explicitly saved (Ctrl+S / Save button).
        if self._active_overlay:
            self._active_overlay._close()
        super().closeEvent(e)
