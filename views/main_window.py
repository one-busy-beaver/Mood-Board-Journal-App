from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel,
)
from PyQt6.QtCore import Qt, QTimer, QPointF
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

        self.setWindowTitle("Journal")
        self.resize(1280, 800)
        self._build_ui()
        self._wire_shortcuts()
        self._wire_controller()
        self._load_saved_notes()
        self._start_autosave()

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
        bar.setFixedHeight(46)
        bar.setStyleSheet(
            "background: #292524; border-bottom: 1px solid #3a3330;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)

        title = QLabel("Journal")
        title.setStyleSheet(
            "color: #f5f5f4; font-size: 14px; font-weight: 600; letter-spacing: 0.5px;"
        )
        layout.addWidget(title)
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

        return bar

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

    def _load_saved_notes(self):
        for note in self._board_ctrl.board.notes:
            self._on_note_added(note)

    def _start_autosave(self):
        timer = QTimer(self)
        timer.timeout.connect(self._autosave)
        timer.start(60_000)

    # ── Note lifecycle ────────────────────────────────────────────────────────

    def _on_note_added(self, note: Note):
        item = NoteItem(note)
        item.removed.connect(self._board_ctrl.remove_note)
        item.expand_requested.connect(self._open_overlay)
        item.geometry_changed.connect(self._on_geometry_changed)
        item.content_changed.connect(self._board_ctrl.update_content)
        item.bring_to_front_requested.connect(self._on_note_focused)
        item.color_change_requested.connect(self._open_color_picker)
        self._canvas.scene.addItem(item)
        self._items[note.id] = item

    def _on_note_removed(self, note_id: str):
        if self._active_note_id == note_id:
            self._active_note_id = None
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

    def _on_overlay_closed(self, note_id: str):
        self._active_overlay = None
        item = self._items.get(note_id)
        if item:
            item.sync_from_model()

    def _on_note_color_changed(self, note_id: str, _color: str):
        item = self._items.get(note_id)
        if item:
            item.update()

    def _open_color_picker(self, note_id: str):
        if self._active_overlay:
            return
        note = next((n for n in self._board_ctrl.board.notes if n.id == note_id), None)
        if note is None:
            return
        overlay = ColorPickerOverlay(note_id, note.color, self._board_ctrl, self, self._shortcuts)
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

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self):
        self._persistence.save(self._board_ctrl.board)
        self._flash_status("Saved")

    def _autosave(self):
        self._persistence.save(self._board_ctrl.board)

    def _flash_status(self, msg: str, ms: int = 2000):
        self._status_label.setText(msg)
        QTimer.singleShot(ms, lambda: self._status_label.setText(""))

    # ── Window events ─────────────────────────────────────────────────────────

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._active_overlay:
            self._active_overlay.setGeometry(self.rect())

    def closeEvent(self, e):
        if self._active_overlay:
            self._active_overlay._close()
        self._save()
        super().closeEvent(e)
