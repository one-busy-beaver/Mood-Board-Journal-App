from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel,
)
from PyQt6.QtCore import Qt, QTimer, QPointF, QSize
from PyQt6.QtGui import QKeySequence, QShortcut

from controllers.board_controller import BoardController
from controllers.persistence_controller import PersistenceController
from models.note import Note
from utils.shortcuts import ShortcutMap, SAVE, NEW_NOTE, DELETE, DELETE_ALT
from utils.shortcuts import REORDER_UP, REORDER_DOWN, REORDER_TO_FRONT, REORDER_TO_BACK
from views.board_canvas import BoardCanvas
from views.note_item import NoteItem
from views.note_overlay import NoteOverlay
from views.color_picker_overlay import ColorPickerOverlay
from views.tools.base_tool import Tool
from views.tools.color_tool import ColorTool


class MainWindow(QMainWindow):
    def __init__(self, board_ctrl: BoardController, persistence: PersistenceController,
                 shortcuts: ShortcutMap):
        super().__init__()
        self._board_ctrl = board_ctrl
        self._persistence = persistence
        self._shortcuts = shortcuts
        self._items: dict[str, NoteItem] = {}
        self._active_overlay: NoteOverlay | None = None
        self._active_note_id: str | None = None
        self._dirty = False

        # Registered toolbar tools (add new ones here)
        self._tools: list[Tool] = [ColorTool()]
        self._tool_buttons: dict[Tool, QPushButton] = {}

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
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        self._canvas = BoardCanvas()
        self._canvas.scene.create_note_requested.connect(self._on_create_at)
        root.addWidget(self._canvas)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(58)
        bar.setStyleSheet(
            "background: #292524; border-bottom: 1px solid #3a3330;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self._make_brand("Journal"))
        layout.addWidget(self._make_divider())

        # ── Tools (icon + name underneath) ──
        for tool in self._tools:
            btn = QPushButton()
            btn.setIcon(tool.icon())
            btn.setIconSize(QSize(22, 22))
            btn.setFixedSize(34, 30)
            btn.setToolTip(tool.tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, t=tool: self._activate_tool(t))
            self._tool_buttons[tool] = btn
            layout.addWidget(self._make_tool(btn, tool.name))

        layout.addStretch()

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #78716c; font-size: 11px;")
        layout.addWidget(self._status_label)
        layout.addSpacing(8)

        add_btn = self._make_btn("+ Note", "#f59e0b", "#d97706", w=76)
        add_btn.setToolTip("New note  (Ctrl+N)")
        add_btn.clicked.connect(self._add_note_center)
        layout.addWidget(add_btn)

        save_btn = self._make_btn("Save", "#44403c", "#57534e", w=58, text_color="#d6d3d1")
        save_btn.setToolTip("Save  (Ctrl+S)")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        self._refresh_tools()
        return bar

    @staticmethod
    def _make_divider() -> QWidget:
        div = QWidget()
        div.setFixedSize(1, 34)
        div.setStyleSheet("background: #3a3330;")
        return div

    @staticmethod
    def _make_brand(text: str) -> QWidget:
        """Title styled with the same two-row geometry as a tool, so its baseline
        lines up with the tool icons rather than floating between icon and caption."""
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(2, 0, 8, 0)
        v.setSpacing(3)
        label = QLabel(text)
        label.setFixedHeight(22)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet(
            "color: #f5f5f4; font-size: 15px; font-weight: 600; "
            "letter-spacing: 0.5px; background: transparent;"
        )
        v.addWidget(label)
        spacer = QLabel("")  # matches the tool caption row height for alignment
        spacer.setFixedHeight(11)
        spacer.setStyleSheet("background: transparent;")
        v.addWidget(spacer)
        return wrap

    @staticmethod
    def _make_tool(widget: QWidget, name: str) -> QWidget:
        """Wrap a tool control with a small caption underneath (toolbar pattern)."""
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(2, 0, 2, 0)
        v.setSpacing(3)
        v.addWidget(widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        caption = QLabel(name)
        caption.setFixedHeight(11)
        caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        caption.setStyleSheet(
            "color: #a8a29e; font-size: 9px; font-weight: 500; background: transparent;"
        )
        v.addWidget(caption)
        return wrap

    def _refresh_tools(self):
        """Re-evaluate each tool's enabled state and dynamic styling."""
        for tool, btn in self._tool_buttons.items():
            btn.setEnabled(tool.is_enabled(self))
            tool.style_button(btn, self)

    def _activate_tool(self, tool: Tool):
        if tool.is_enabled(self):
            tool.activate(self)

    @staticmethod
    def _make_btn(text: str, bg: str, hover: str, w: int = 72,
                  text_color: str = "white") -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(w, 30)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {text_color};
                border: none;
                border-radius: 5px;
                font-size: 12px;
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

    def _wire_controller(self):
        self._board_ctrl.note_added.connect(self._on_note_added)
        self._board_ctrl.note_removed.connect(self._on_note_removed)
        self._board_ctrl.z_order_changed.connect(self._on_z_changed)
        self._board_ctrl.note_color_changed.connect(self._on_note_color_changed)
        # Any model mutation marks the board dirty (persisted only on explicit Save)
        self._board_ctrl.board_changed.connect(self._on_board_changed)

    def _load_saved_notes(self):
        for note in self._board_ctrl.board.notes:
            self._on_note_added(note)
        # Loading isn't a user edit — start clean
        self._dirty = False

    # ── Note lifecycle ────────────────────────────────────────────────────────

    def _on_note_added(self, note: Note):
        item = NoteItem(note)
        item.removed.connect(self._board_ctrl.remove_note)
        item.expand_requested.connect(self._open_overlay)
        item.geometry_changed.connect(self._on_geometry_changed)
        item.content_changed.connect(self._board_ctrl.update_content)
        item.bring_to_front_requested.connect(self._on_note_focused)
        self._canvas.scene.addItem(item)
        self._items[note.id] = item

    def _on_note_removed(self, note_id: str):
        if self._active_note_id == note_id:
            self._active_note_id = None
            self._refresh_tools()
        item = self._items.pop(note_id, None)
        if item:
            self._canvas.scene.removeItem(item)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _add_note_center(self):
        if self._active_overlay:
            return
        center = self._canvas.mapToScene(
            self._canvas.viewport().rect().center()
        )
        self._board_ctrl.create_note(center.x() - 120, center.y() - 100)

    def _on_create_at(self, x: float, y: float):
        self._board_ctrl.create_note(x - 120, y - 100)

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
        self._refresh_tools()

    def _on_overlay_closed(self, note_id: str):
        self._active_overlay = None
        item = self._items.get(note_id)
        if item:
            item.sync_from_model()

    def _on_note_color_changed(self, note_id: str, _color: str):
        item = self._items.get(note_id)
        if item:
            item.update()
        if note_id == self._active_note_id:
            self._refresh_tools()

    # ── Public interface used by Tools ────────────────────────────────────────

    def active_note(self) -> Note | None:
        if self._active_note_id is None:
            return None
        return next(
            (n for n in self._board_ctrl.board.notes if n.id == self._active_note_id),
            None,
        )

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
        item = self._items.get(note_id)
        if item:
            item.setZValue(z)

    def _on_geometry_changed(self, note_id: str, x: float, y: float,
                              w: float, h: float):
        self._board_ctrl.update_geometry(note_id, x=x, y=y, width=w, height=h)

    def _delete_selected(self):
        if self._active_overlay:
            return
        for item in list(self._canvas.scene.selectedItems()):
            if isinstance(item, NoteItem):
                self._board_ctrl.remove_note(item.note_id)

    # ── Z-order reordering ────────────────────────────────────────────────────

    def _selected_note_id(self) -> str | None:
        return self._active_note_id

    def _reorder_up(self):
        if self._active_overlay:
            return
        note_id = self._selected_note_id()
        if note_id:
            self._board_ctrl.reorder_one_up(note_id)

    def _reorder_down(self):
        if self._active_overlay:
            return
        note_id = self._selected_note_id()
        if note_id:
            self._board_ctrl.reorder_one_down(note_id)

    def _reorder_to_front(self):
        if self._active_overlay:
            return
        note_id = self._selected_note_id()
        if note_id:
            self._board_ctrl.bring_to_front(note_id)

    def _reorder_to_back(self):
        if self._active_overlay:
            return
        note_id = self._selected_note_id()
        if note_id:
            self._board_ctrl.send_to_back(note_id)

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
