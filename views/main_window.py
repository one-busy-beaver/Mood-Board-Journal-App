from dataclasses import dataclass, field

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QLabel, QApplication, QTextEdit, QLineEdit,
)
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QShortcut

from controllers.board_controller import BoardController
from controllers.library_controller import LibraryController
from controllers.settings_controller import SettingsController
from controllers.persistence_controller import PersistenceController
from models.note import Note
from models.journal import Journal
from utils.shortcuts import ShortcutMap, SAVE, NEW_NOTE, DELETE, DELETE_ALT
from utils.shortcuts import REORDER_UP, REORDER_DOWN, REORDER_TO_FRONT, REORDER_TO_BACK
from utils.shortcuts import SCALE_UP, SCALE_DOWN, SCALE_RESET
from utils.shortcuts import TOGGLE_SIDEBAR, NEW_JOURNAL, CLOSE_TAB
from views.workspace import Workspace
from views.widgets.selection_frame import SelectionFrame
from views.note_overlay import NoteOverlay
from views.color_panel import ColorPanel
from views.explorer_panel import ExplorerPanel
from views.tab_bar import TabBar
from views.confirm_overlay import ConfirmOverlay
from views.tools.base_tool import Tool
from views.tools.color_tool import ColorTool
from views.tools.font_size_tool import FontSizeTool


@dataclass
class JournalSession:
    """One open journal (one tab). Like a VSCode editor tab, a session stays
    alive in memory while other journals are shown, keeping its own controller,
    workspace, dirty flag and active-note selection."""
    node_id: str
    journal: Journal
    controller: BoardController
    workspace: Workspace
    frame: SelectionFrame
    dirty: bool = False
    active_note_id: str | None = None


class MainWindow(QMainWindow):
    DEFAULT_NOTE_W = 240
    DEFAULT_NOTE_H = 200

    def __init__(self, library_ctrl: LibraryController,
                 settings_ctrl: SettingsController,
                 persistence: PersistenceController, shortcuts: ShortcutMap):
        super().__init__()
        self._library_ctrl = library_ctrl
        self._settings_ctrl = settings_ctrl
        self._persistence = persistence
        self._shortcuts = shortcuts
        self._active_overlay = None

        # Open journals, in tab order. The active one drives the toolbar/tools.
        self._sessions: dict[str, JournalSession] = {}
        self._tab_order: list[str] = []
        self._active_id: str | None = None
        self._sidebar_visible = True

        # Registered toolbar tools (add new ones here)
        self._tools: list[Tool] = [ColorTool(), FontSizeTool()]

        self.setWindowTitle("Journal")
        self.resize(1360, 840)
        self._build_ui()
        self._wire_shortcuts()
        self._wire_library()
        self._open_initial_journal()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet("QMainWindow { background: #1c1917; }")
        central = QWidget()
        self.setCentralWidget(central)

        # The toolbar spans the FULL window width; the explorer sits beneath it,
        # so opening/closing the sidebar never shifts or resizes the toolbar.
        self._root_layout = QVBoxLayout(central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        self._toolbar = self._build_toolbar()
        self._root_layout.addWidget(self._toolbar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._explorer = ExplorerPanel(self._library_ctrl.library, self.ui_scale())
        self._explorer.journal_opened.connect(self.open_journal)
        self._explorer.folder_toggled.connect(self._on_folder_toggled)
        self._explorer.new_journal_requested.connect(self._on_new_journal)
        self._explorer.new_folder_requested.connect(self._library_ctrl.create_folder)
        self._explorer.move_requested.connect(self._on_move)
        self._explorer.rename_requested.connect(self._on_rename)
        self._explorer.delete_requested.connect(self._confirm_delete)
        body_layout.addWidget(self._explorer)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._tab_bar = TabBar(self.ui_scale())
        self._tab_bar.tab_selected.connect(self.open_journal)
        self._tab_bar.tab_close_requested.connect(self.close_journal)
        right_layout.addWidget(self._tab_bar)

        # One page per open journal; switching tabs swaps the visible page
        # without destroying the others.
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: #1c1917;")
        right_layout.addWidget(self._stack, 1)

        self._empty_page = self._build_empty_page()
        self._stack.addWidget(self._empty_page)

        body_layout.addWidget(right, 1)
        self._root_layout.addWidget(body, 1)

    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: #1c1917;")
        v = QVBoxLayout(page)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel("No journal open\n\nPick one from the explorer, or press Ctrl+Shift+N")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #57534e; font-size: 13px; background: transparent;")
        v.addWidget(label)
        return page

    def ui_scale(self) -> float:
        """App-wide UI zoom ('resolution'): scales the toolbar, sidebar, tab bar
        and note boxes, but NOT the body text (that's per-note font_size).

        One value for the whole application — it scales chrome shared by every
        journal, so it is stored in Settings, not per journal."""
        return self._settings_ctrl.scale

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
        bar = QWidget()
        bar.setFixedHeight(self._px(58))
        bar.setStyleSheet("background: #292524; border-bottom: 1px solid #3a3330;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(self._px(10), 0, self._px(14), 0)
        layout.setSpacing(self._px(6))
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._sidebar_btn = self._make_btn("☰", "#44403c", "#57534e", w=self._px(34),
                                           text_color="#d6d3d1")
        self._sidebar_btn.setToolTip(
            f"Toggle explorer  ({self._shortcuts.binding_str(TOGGLE_SIDEBAR)})"
        )
        self._sidebar_btn.clicked.connect(self.toggle_sidebar)
        layout.addWidget(self._sidebar_btn)

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
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        bind(SCALE_UP,         lambda: self._nudge_scale(+1))
        bind(SCALE_DOWN,       lambda: self._nudge_scale(-1))
        bind(SCALE_RESET,      self._reset_scale)
        bind(TOGGLE_SIDEBAR,   self.toggle_sidebar)
        bind(NEW_JOURNAL,      lambda: self._on_new_journal("root"))
        bind(CLOSE_TAB,        self._close_active_tab)

    def _wire_library(self):
        self._library_ctrl.library_changed.connect(self._on_library_changed)
        self._settings_ctrl.scale_changed.connect(self._on_scale_changed)

    # ── Journal sessions (tabs) ───────────────────────────────────────────────

    def _open_initial_journal(self):
        journals = self._library_ctrl.library.journals()
        if journals:
            self.open_journal(journals[0].id)
        else:
            self._show_active_page()

    def open_journal(self, node_id: str):
        """Open (or focus) a journal. Already-open journals are simply revealed —
        switching never saves, prompts, or discards."""
        node = self._library_ctrl.find(node_id)
        if node is None or node.is_folder:
            return

        if node_id not in self._sessions:
            self._create_session(node_id, node.name)  # registers itself
            self._tab_order.append(node_id)

        self._active_id = node_id
        self._show_active_page()
        self._rebuild_toolbar()
        self._refresh_chrome()

    def _create_session(self, node_id: str, name: str) -> JournalSession:
        journal = self._persistence.load_journal(node_id, name)
        journal.title = name
        controller = BoardController(journal)
        workspace = Workspace(self.ui_scale())
        workspace.create_note_requested.connect(
            lambda x, y, w, h, nid=node_id: self._on_create_at(nid, x, y, w, h)
        )
        workspace.background_clicked.connect(
            lambda nid=node_id: self._on_background_clicked(nid)
        )

        # Selection chrome lives above every note so its handles are never
        # buried by an overlapping note.
        frame = SelectionFrame(workspace)
        workspace.set_selection_frame(frame)
        frame.resized.connect(
            lambda nid, x, y, w, h, jid=node_id: self._on_frame_resized(jid, nid, x, y, w, h)
        )
        frame.rotated.connect(
            lambda nid, deg, jid=node_id: self._on_frame_rotated(jid, nid, deg)
        )
        frame.interaction_finished.connect(
            lambda nid, jid=node_id: self._on_frame_finished(jid, nid)
        )
        self._stack.addWidget(workspace)

        session = JournalSession(node_id, journal, controller, workspace, frame)
        # Register before loading notes — _on_note_added resolves the session by
        # id, so it has to be findable already.
        self._sessions[node_id] = session

        controller.note_added.connect(
            lambda note, nid=node_id: self._on_note_added(nid, note)
        )
        controller.note_removed.connect(
            lambda note_id, nid=node_id: self._on_note_removed(nid, note_id)
        )
        controller.z_order_changed.connect(
            lambda *_, nid=node_id: self._session(nid).workspace.restack()
        )
        controller.note_color_changed.connect(
            lambda note_id, c, nid=node_id: self._on_note_color_changed(nid, note_id)
        )
        controller.note_font_changed.connect(
            lambda note_id, s, nid=node_id: self._on_note_font_changed(nid, note_id)
        )
        controller.board_changed.connect(
            lambda nid=node_id: self._on_board_changed(nid)
        )

        for note in journal.notes:
            self._on_note_added(node_id, note)
        workspace.restack()
        # Clamping stray notes into view fires geometry updates; neither that nor
        # loading is a user edit, so clear the flag once the layout settles.
        session.dirty = False
        QTimer.singleShot(0, lambda sid=node_id: self._clear_initial_dirty(sid))
        return session

    def _clear_initial_dirty(self, node_id: str):
        session = self._sessions.get(node_id)
        if session is not None:
            session.dirty = False
            self._refresh_chrome()

    def close_journal(self, node_id: str):
        """Close a tab. This — not switching — is what prompts when dirty."""
        session = self._sessions.get(node_id)
        if session is None:
            return
        if session.dirty:
            self._prompt_unsaved(session)
            return
        self._discard_session(node_id)

    def _prompt_unsaved(self, session: JournalSession):
        name = self._library_ctrl.name_of(session.node_id)
        node_id = session.node_id

        def save_then_close():
            self._persistence.save_journal(session.journal)
            self._discard_session(node_id)

        self._show_overlay(ConfirmOverlay(
            self, self._shortcuts,
            f"Save changes to “{name}”?",
            "Your changes will be lost if you close without saving.",
            [
                ("Save", "primary", save_then_close),
                ("Don't Save", "danger", lambda: self._discard_session(node_id)),
                ("Cancel", "ghost", None),
            ],
        ))

    def _discard_session(self, node_id: str):
        session = self._sessions.pop(node_id, None)
        if session is None:
            return
        if node_id in self._tab_order:
            self._tab_order.remove(node_id)
        self._stack.removeWidget(session.workspace)
        session.workspace.deleteLater()

        if self._active_id == node_id:
            self._active_id = self._tab_order[-1] if self._tab_order else None

        self._show_active_page()
        self._rebuild_toolbar()
        self._refresh_chrome()

    def _close_active_tab(self):
        if self._active_id and not self._active_overlay:
            self.close_journal(self._active_id)

    def _session(self, node_id: str | None = None) -> JournalSession | None:
        return self._sessions.get(node_id or self._active_id or "")

    @property
    def _active(self) -> JournalSession | None:
        return self._session()

    def _show_active_page(self):
        session = self._active
        self._stack.setCurrentWidget(
            session.workspace if session else self._empty_page
        )

    def _refresh_chrome(self):
        """Re-render tab bar + explorer to match session state."""
        tabs = [
            (nid, self._library_ctrl.name_of(nid), self._sessions[nid].dirty)
            for nid in self._tab_order if nid in self._sessions
        ]
        self._tab_bar.render_tabs(tabs, self._active_id)
        self._explorer.set_dirty_ids(
            {nid for nid, s in self._sessions.items() if s.dirty}
        )
        self._explorer.set_active(self._active_id)
        self._update_dirty_indicator()
        self._refresh_tools()
        name = self._library_ctrl.name_of(self._active_id) if self._active_id else None
        self.setWindowTitle(f"Journal — {name}" if name else "Journal")

    # ── Explorer actions ──────────────────────────────────────────────────────

    def _on_library_changed(self):
        self._explorer.render_tree()
        self._refresh_chrome()

    def _on_folder_toggled(self, node_id: str):
        self._library_ctrl.toggle_folder(node_id)

    def _on_new_journal(self, parent_id: str):
        node = self._library_ctrl.create_journal(parent_id)
        self.open_journal(node.id)
        self._explorer.begin_rename(node.id)

    def _on_move(self, node_id: str, new_parent_id: str):
        """Drag-and-drop in the explorer. Invalid drops (into itself or its own
        subtree) are refused by the controller and simply do nothing."""
        self._library_ctrl.move(node_id, new_parent_id)

    def _on_rename(self, node_id: str, name: str):
        self._library_ctrl.rename(node_id, name)
        session = self._sessions.get(node_id)
        if session:
            session.journal.title = name

    def _confirm_delete(self, node_id: str):
        node = self._library_ctrl.find(node_id)
        if node is None:
            return
        kind = "folder" if node.is_folder else "journal"
        extra = " and everything inside it" if node.is_folder else ""
        self._show_overlay(ConfirmOverlay(
            self, self._shortcuts,
            f"Delete “{node.name}”?",
            f"This {kind}{extra} will be permanently deleted. This cannot be undone.",
            [
                ("Delete", "danger", lambda: self._do_delete(node_id)),
                ("Cancel", "ghost", None),
            ],
        ))

    def _do_delete(self, node_id: str):
        node = self._library_ctrl.find(node_id)
        removed_ids = [n.id for n in node.walk()] if node else [node_id]
        for jid in removed_ids:
            # Drop without prompting: the user already confirmed deletion.
            if jid in self._sessions:
                self._discard_session(jid)
        self._library_ctrl.delete(node_id)

    def toggle_sidebar(self):
        self._sidebar_visible = not self._sidebar_visible
        self._explorer.setVisible(self._sidebar_visible)

    # ── Note lifecycle ────────────────────────────────────────────────────────

    def _on_note_added(self, node_id: str, note: Note):
        session = self._session(node_id)
        if session is None:
            return
        win = session.workspace.add_note(note)
        win.removed.connect(session.controller.remove_note)
        win.expand_requested.connect(
            lambda nid, jid=node_id: self._open_overlay(jid, nid)
        )
        win.geometry_changed.connect(
            lambda *a, jid=node_id: self._on_geometry_changed(jid, *a)
        )
        win.content_changed.connect(session.controller.update_content)
        win.bring_to_front_requested.connect(
            lambda nid, jid=node_id: self._on_note_focused(jid, nid)
        )
        win.moved.connect(lambda nid, jid=node_id: self._sync_frame(jid, nid))

    def _on_note_removed(self, node_id: str, note_id: str):
        session = self._session(node_id)
        if session is None:
            return
        if session.active_note_id == note_id:
            session.active_note_id = None
            session.frame.detach()
            self._refresh_tools()
        session.workspace.remove_note(note_id)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _add_note_center(self):
        session = self._active
        if self._active_overlay or session is None:
            return
        # Convert the on-screen center to base (unscaled) coords the model stores.
        s = self.ui_scale()
        c = session.workspace.rect().center()
        session.controller.create_note(
            max(0, c.x() / s - self.DEFAULT_NOTE_W / 2),
            max(0, c.y() / s - self.DEFAULT_NOTE_H / 2),
        )

    def _on_create_at(self, node_id: str, x: float, y: float,
                      w: float = 0.0, h: float = 0.0):
        """Create a note from a workspace gesture.

        A double-click sends w/h = 0 and gets a default-sized note centred on
        the cursor; a drag sends the dragged box, which is used as-is (already
        clamped to the minimum by the workspace)."""
        session = self._session(node_id)
        if session is None or self._active_overlay:
            return
        s = self.ui_scale()
        if w > 0 and h > 0:
            session.controller.create_note(max(0, x / s), max(0, y / s),
                                           width=w / s, height=h / s)
        else:
            session.controller.create_note(
                max(0, x / s - self.DEFAULT_NOTE_W / 2),
                max(0, y / s - self.DEFAULT_NOTE_H / 2),
            )

    def _open_overlay(self, node_id: str, note_id: str):
        session = self._session(node_id)
        if self._active_overlay or session is None:
            return
        note = next((n for n in session.journal.notes if n.id == note_id), None)
        if note is None:
            return
        overlay = NoteOverlay(note, session.controller, self, self._shortcuts)
        # The editor can raise its own "unsaved changes" dialog; track that as
        # the active overlay while it is up, then hand control back.
        def _nested(dialog, ov=overlay):
            self._active_overlay = dialog
            dialog.closed.connect(
                lambda: setattr(self, "_active_overlay",
                                ov if ov.isVisible() else None))
        overlay.dialog_opened = _nested
        self._show_overlay(overlay)
        overlay.closed.connect(lambda: self._on_overlay_closed(node_id, note_id))

    def _on_note_focused(self, node_id: str, note_id: str):
        session = self._session(node_id)
        if session is None:
            return
        self._explorer.commit_rename()   # clicking a note ends any rename
        previous = session.active_note_id
        if previous and previous != note_id:
            prev_win = session.workspace.window(previous)
            if prev_win:
                prev_win.set_selected(False)
        session.active_note_id = note_id
        win = session.workspace.window(note_id)
        if win:
            win.set_selected(True)
            # Selection chrome floats above every note (the note itself keeps
            # its own stacking depth — clicking never raises it).
            session.frame.attach(note_id, QRectF(win.geometry()), win.angle())
            session.frame.raise_()
        self._refresh_tools()

    def _sync_frame(self, node_id: str, note_id: str):
        """Keep the selection frame glued to its note while it is dragged."""
        session = self._session(node_id)
        if session is None or session.active_note_id != note_id:
            return
        win = session.workspace.window(note_id)
        if win is not None:
            session.frame.update_geometry(QRectF(win.geometry()), win.angle())

    def _on_frame_resized(self, node_id: str, note_id: str,
                          x: float, y: float, w: float, h: float):
        """Live resize from a handle — move the widget now, commit on release."""
        session = self._session(node_id)
        if session is None:
            return
        win = session.workspace.window(note_id)
        if win is not None:
            win.set_scene_rect(x, y, w, h)
            session.workspace.update()   # repaint rotated snapshots

    def _on_frame_rotated(self, node_id: str, note_id: str, degrees: float):
        session = self._session(node_id)
        if session is None:
            return
        session.controller.update_geometry(note_id, rotation=degrees)
        session.workspace.refresh_rotation(note_id)

    def _on_frame_finished(self, node_id: str, note_id: str):
        """Commit a resize/rotate to the model once the gesture ends."""
        session = self._session(node_id)
        if session is None:
            return
        win = session.workspace.window(note_id)
        if win is not None:
            win.emit_geometry()
            session.workspace.refresh_rotation(note_id)
            session.frame.update_geometry(QRectF(win.geometry()), win.angle())

    def _on_background_clicked(self, node_id: str):
        """Clicking empty canvas deselects the active note, so the selection
        border clears and note-scoped tools (colour, font) go inactive."""
        # Clicking outside the sidebar also finishes an open rename.
        self._explorer.commit_rename()
        session = self._session(node_id)
        if session is None or self._active_overlay:
            return
        if session.active_note_id is None:
            return
        session.workspace.clear_selection()
        session.frame.detach()
        session.active_note_id = None
        self._refresh_tools()

    def _on_overlay_closed(self, node_id: str, note_id: str):
        self._active_overlay = None
        session = self._session(node_id)
        win = session.workspace.window(note_id) if session else None
        if win:
            win.sync_from_model()

    def _on_note_color_changed(self, node_id: str, note_id: str):
        session = self._session(node_id)
        if session is None:
            return
        win = session.workspace.window(note_id)
        if win:
            win.refresh_color()
        if note_id == session.active_note_id:
            self._refresh_tools()

    def _on_note_font_changed(self, node_id: str, note_id: str):
        session = self._session(node_id)
        if session is None:
            return
        win = session.workspace.window(note_id)
        if win:
            win.apply_font()
        if note_id == session.active_note_id:
            self._refresh_tools()

    def _on_scale_changed(self, scale: float):
        """One app-wide zoom: re-scale the shared chrome and EVERY open journal,
        so switching tabs never resizes the window furniture."""
        for session in self._sessions.values():
            session.workspace.apply_scale(scale)  # note geometry (not body font)
            session.frame.detach()                # handles would be stale
            session.active_note_id = None
        self._explorer.apply_scale(scale)
        self._tab_bar.apply_scale(scale)
        self._rebuild_toolbar()
        self._refresh_chrome()

    def _nudge_scale(self, direction: int):
        self._settings_ctrl.nudge_scale(direction)

    def _reset_scale(self):
        self._settings_ctrl.reset_scale()

    # ── Public interface used by Tools ────────────────────────────────────────

    def active_note(self) -> Note | None:
        session = self._active
        if session is None or session.active_note_id is None:
            return None
        return next(
            (n for n in session.journal.notes if n.id == session.active_note_id), None
        )

    def change_active_font(self, delta: int):
        session = self._active
        note = self.active_note()
        if session is None or note is None:
            return
        session.controller.update_font_size(note.id, note.font_size + delta)

    def open_color_picker_for_active(self, anchor=None):
        session = self._active
        if self._active_overlay or session is None:
            return
        note = self.active_note()
        if note is None:
            self._flash_status("Select a note first")
            return
        panel = ColorPanel(
            note.id, note.color, session.controller, self._settings_ctrl,
            self, self._shortcuts, anchor
        )
        panel.color_applied.connect(self._on_color_applied)
        self._show_overlay(panel)
        panel.closed.connect(lambda: setattr(self, "_active_overlay", None))

    def _show_overlay(self, overlay):
        # An in-flight resize/rotate would otherwise keep receiving the mouse
        # (and could hold a grab), leaving the dialog's buttons unclickable.
        self._release_canvas_gestures()
        self._active_overlay = overlay
        overlay.closed.connect(self._clear_overlay)

    def _release_canvas_gestures(self):
        """Abandon any half-finished drag/resize/rotate in every open journal.

        Called before showing a dialog and before quitting: a gesture that never
        received its mouse-release would otherwise swallow clicks app-wide."""
        for session in self._sessions.values():
            session.frame.cancel_gesture()
            session.workspace.cancel_gestures()

    def _clear_overlay(self):
        self._active_overlay = None

    def _on_color_applied(self, hex_color: str):
        """A colour was committed from the panel. Today the target is the active
        note; other object types can be routed from here later."""
        self._flash_status(f"Applied {hex_color.upper()}")

    def _on_geometry_changed(self, node_id: str, note_id: str, x: float, y: float,
                             w: float, h: float):
        session = self._session(node_id)
        if session:
            session.controller.update_geometry(note_id, x=x, y=y, width=w, height=h)

    def _delete_selected(self):
        session = self._active
        if self._active_overlay or self._editing_text() or session is None:
            return
        if session.active_note_id:
            session.controller.remove_note(session.active_note_id)

    # ── Z-order reordering ────────────────────────────────────────────────────

    @staticmethod
    def _editing_text() -> bool:
        """True while a text field has focus, so note-management shortcuts
        (delete, reorder) defer to normal text editing."""
        return isinstance(QApplication.focusWidget(), (QTextEdit, QLineEdit))

    def _reorder(self, action_name: str):
        session = self._active
        if self._active_overlay or self._editing_text() or session is None:
            return
        if session.active_note_id:
            getattr(session.controller, action_name)(session.active_note_id)

    def _reorder_up(self):
        self._reorder("reorder_one_up")

    def _reorder_down(self):
        self._reorder("reorder_one_down")

    def _reorder_to_front(self):
        self._reorder("bring_to_front")

    def _reorder_to_back(self):
        self._reorder("send_to_back")

    # ── Persistence (explicit save only — no autosave, no save-on-close) ──────

    def _on_board_changed(self, node_id: str):
        session = self._session(node_id)
        if session is None:
            return
        session.dirty = True
        self._refresh_chrome()

    def _save(self):
        """Ctrl+S. A window-scoped shortcut always wins over anything inside an
        overlay, so route the key to the overlay when one is open — otherwise the
        note editor's own save could never fire."""
        overlay = self._active_overlay
        if overlay is not None and hasattr(overlay, "_save"):
            overlay._save()
            return
        session = self._active
        if session is None:
            return
        self._persistence.save_journal(session.journal)
        session.dirty = False
        self._refresh_chrome()
        self._status_label.setText("Saved ✓")
        self._status_label.setStyleSheet(
            f"color: #6ee7b7; font-size: {self._px(11)}px;")
        QTimer.singleShot(1500, self._update_dirty_indicator)

    def _update_dirty_indicator(self):
        session = self._active
        if session is not None and session.dirty:
            self._status_label.setText("● Unsaved")
            self._status_label.setStyleSheet(
                f"color: #f59e0b; font-size: {self._px(11)}px;")
        else:
            self._status_label.setText("")
            self._status_label.setStyleSheet(
                f"color: #78716c; font-size: {self._px(11)}px;")

    def _flash_status(self, msg: str, ms: int = 2000):
        self._status_label.setText(msg)
        self._status_label.setStyleSheet(
            f"color: #78716c; font-size: {self._px(11)}px;")
        QTimer.singleShot(ms, self._update_dirty_indicator)

    # ── Window events ─────────────────────────────────────────────────────────

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._active_overlay:
            self._active_overlay.setGeometry(self.rect())

    def closeEvent(self, e):
        """Unlike switching tabs, quitting with unsaved work prompts once —
        otherwise closing still discards (no autosave, no save-on-close)."""
        self._release_canvas_gestures()
        dirty = [s for s in self._sessions.values() if s.dirty]
        if dirty and not getattr(self, "_force_close", False):
            e.ignore()
            names = ", ".join(self._library_ctrl.name_of(s.node_id) for s in dirty)

            def save_all():
                for s in dirty:
                    self._persistence.save_journal(s.journal)
                    s.dirty = False
                self._force_close = True
                self.close()

            def discard_all():
                self._force_close = True
                self.close()

            self._show_overlay(ConfirmOverlay(
                self, self._shortcuts,
                "Save before quitting?",
                f"Unsaved changes in: {names}",
                [
                    ("Save All", "primary", save_all),
                    ("Don't Save", "danger", discard_all),
                    ("Cancel", "ghost", None),
                ],
            ))
            return

        if self._active_overlay:
            self._active_overlay._close()
        super().closeEvent(e)
