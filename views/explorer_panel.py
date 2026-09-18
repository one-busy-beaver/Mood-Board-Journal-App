"""VSCode-style file explorer for the journal library.

A collapsible left sidebar listing folders and journals. Journals open on a
single click; folders toggle open/closed. A right-click context menu (rendered
in-app, never an OS popup) offers New Journal / New Folder / Rename / Delete.

The panel is a pure view over `Library`: it emits intent signals and re-renders
when told to. All mutation goes through MainWindow → LibraryController.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QLineEdit, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QMimeData, QEvent, QPointF
from PyQt6.QtGui import QCursor, QDrag
from PyQt6.QtWidgets import QApplication

from models.library import Library, LibraryNode, FOLDER, JOURNAL

# Palette shared with the toolbar's dark chrome.
BG = "#1a1817"
FG = "#d6d3d1"
FG_DIM = "#a8a29e"
ACTIVE_BG = "#3a3330"
HOVER_BG = "#292524"
ACCENT = "#f59e0b"


class _RowWidget(QWidget):
    """One tree row: chevron (folders) + icon + name, indented by depth.

    Rows render their own hover/active background rather than using a stylesheet
    pseudo-class, because the row is a composite widget.
    """

    clicked = pyqtSignal(str)          # node_id
    double_clicked = pyqtSignal(str)   # node_id
    context_requested = pyqtSignal(str, object)  # node_id, global QPoint

    INDENT = 12
    MIME = "application/x-journal-node"

    def __init__(self, node: LibraryNode, depth: int, active: bool,
                 dirty: bool, scale: float, parent=None, drop_target: bool = False):
        super().__init__(parent)
        self._node = node
        self._active = active
        self._drop_target = drop_target
        self._hover = False
        self._press_pos = None
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(max(22, round(24 * scale)))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QHBoxLayout(self)
        pad = round(6 * scale) + depth * round(self.INDENT * scale)
        lay.setContentsMargins(pad, 0, round(6 * scale), 0)
        lay.setSpacing(round(4 * scale))

        font_px = max(10, round(12 * scale))

        glyph = ("▾" if node.expanded else "▸") if node.is_folder else ""
        chevron = QLabel(glyph)
        chevron.setFixedWidth(round(12 * scale))
        chevron.setStyleSheet(
            f"color: {FG_DIM}; font-size: {max(8, round(9 * scale))}px; "
            "background: transparent;"
        )
        lay.addWidget(chevron)

        icon = QLabel("🗀" if node.is_folder else "▤")
        icon.setStyleSheet(
            f"color: {ACCENT if node.is_folder else FG_DIM}; "
            f"font-size: {font_px}px; background: transparent;"
        )
        lay.addWidget(icon)

        self._name_label = name = QLabel(node.name + (" ●" if dirty else ""))
        name.setStyleSheet(
            f"color: {FG if (active or node.is_folder) else FG_DIM}; "
            f"font-size: {font_px}px; background: transparent; "
            f"font-weight: {'600' if active else '400'};"
        )
        lay.addWidget(name)
        lay.addStretch()

        self._update_bg()

    def node_id(self) -> str:
        return self._node.id

    def set_state(self, active: bool, dirty: bool, drop_target: bool):
        """Re-style in place — cheaper than a rebuild, and it keeps the widget
        alive through a press so a drag can start from it."""
        if (active, drop_target) != (self._active, self._drop_target):
            self._active, self._drop_target = active, drop_target
            self._update_bg()
        label = self._node.name + (" ●" if dirty else "")
        if self._name_label.text() != label:
            self._name_label.setText(label)

    def _update_bg(self):
        if self._drop_target:
            # The folder a drag is currently hovering over.
            self.setStyleSheet(
                f"_RowWidget {{ background: {HOVER_BG}; "
                f"border: 1px solid {ACCENT}; border-radius: 3px; }}")
            return
        if self._active:
            bg = ACTIVE_BG
        elif self._hover:
            bg = HOVER_BG
        else:
            bg = "transparent"
        self.setStyleSheet(f"_RowWidget {{ background: {bg}; }}")

    def enterEvent(self, e):
        self._hover = True
        self._update_bg()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._update_bg()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.position().toPoint()
            self.clicked.emit(self._node.id)
            e.accept()
        elif e.button() == Qt.MouseButton.RightButton:
            self.context_requested.emit(self._node.id, e.globalPosition().toPoint())
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        """Begin a drag once the pointer has moved past the drag threshold, so a
        plain click still selects."""
        if (self._press_pos is None
                or not (e.buttons() & Qt.MouseButton.LeftButton)):
            return super().mouseMoveEvent(e)
        if ((e.position().toPoint() - self._press_pos).manhattanLength()
                < QApplication.startDragDistance()):
            return super().mouseMoveEvent(e)

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self.MIME, self._node.id.encode("utf-8"))
        mime.setText(self._node.name)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(self._press_pos)
        self._press_pos = None
        drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, e):
        self._press_pos = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = None
            self.double_clicked.emit(self._node.id)
            e.accept()
            return
        super().mouseDoubleClickEvent(e)


class _TranslatedDrag:
    """Adapts a drag event to a different coordinate space.

    The panel's drag handlers only need `position()`, `mimeData()` and the
    accept/ignore calls, so this thin wrapper is enough to reuse them for events
    that arrived on a child widget.
    """

    def __init__(self, event, pos):
        self._event = event
        self._pos = QPointF(pos)
        self._accepted = False

    def position(self) -> QPointF:
        return self._pos

    def mimeData(self):
        return self._event.mimeData()

    def acceptProposedAction(self):
        self._accepted = True

    def accept(self):
        self._accepted = True

    def ignore(self):
        self._accepted = False

    def is_accepted(self) -> bool:
        return self._accepted


class ExplorerPanel(QWidget):
    """The sidebar itself. Emits intent; never mutates the library directly."""

    journal_opened = pyqtSignal(str)                 # node_id
    folder_toggled = pyqtSignal(str)                 # node_id
    new_journal_requested = pyqtSignal(str)          # parent_id ("root" for top)
    new_folder_requested = pyqtSignal(str)           # parent_id
    move_requested = pyqtSignal(str, str)            # node_id, new_parent_id
    rename_requested = pyqtSignal(str, str)          # node_id, new_name
    delete_requested = pyqtSignal(str)               # node_id

    BASE_W = 240

    def __init__(self, library: Library, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._library = library
        self._scale = scale
        self._active_id: str | None = None
        # The row the user last clicked — a folder here is where new items go.
        # Distinct from _active_id, which is the journal currently OPEN.
        self._selected_id: str | None = None
        self._drop_target_id: str | None = None   # folder highlighted mid-drag
        self._dirty_ids: set[str] = set()
        self._renaming_id: str | None = None
        self._active_rename_commit = None   # closure that saves the open editor
        self._menu: QWidget | None = None

        self.setStyleSheet(f"background: {BG};")
        self.setFixedWidth(round(self.BASE_W * scale))
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG}; border: none; }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: #44403c; border-radius: 3px; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        """)
        self._tree_host = QWidget()
        self._tree_host.setStyleSheet(f"background: {BG};")
        # Rows sit inside the scroll area, so its viewport — not just this panel
        # — has to accept drops, or it swallows the drag before we see it.
        self._tree_host.setAcceptDrops(True)
        self._tree_host.installEventFilter(self)
        self._tree_layout = QVBoxLayout(self._tree_host)
        self._tree_layout.setContentsMargins(0, round(4 * scale), 0, 0)
        self._tree_layout.setSpacing(0)
        self._tree_layout.addStretch()
        self._scroll.setWidget(self._tree_host)
        self._scroll.viewport().setAcceptDrops(True)
        self._scroll.viewport().installEventFilter(self)
        root.addWidget(self._scroll, 1)

        self.render_tree()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        s = self._scale
        bar = QWidget()
        bar.setFixedHeight(round(34 * s))
        bar.setStyleSheet(f"background: {BG}; border-bottom: 1px solid #292524;")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(round(10 * s), 0, round(6 * s), 0)
        lay.setSpacing(round(2 * s))

        label = QLabel("EXPLORER")
        label.setStyleSheet(
            f"color: {FG_DIM}; font-size: {max(8, round(10 * s))}px; "
            "font-weight: 700; letter-spacing: 1px; background: transparent;"
        )
        lay.addWidget(label)
        lay.addStretch()

        new_j = self._icon_btn("＋", "New journal (in the selected folder)")
        new_j.clicked.connect(
            lambda: self.new_journal_requested.emit(self.target_parent()))
        lay.addWidget(new_j)

        new_f = self._icon_btn("🗀", "New folder (in the selected folder)")
        new_f.clicked.connect(
            lambda: self.new_folder_requested.emit(self.target_parent()))
        lay.addWidget(new_f)
        return bar

    def _icon_btn(self, glyph: str, tip: str) -> QPushButton:
        s = self._scale
        b = QPushButton(glyph)
        b.setToolTip(tip)
        b.setFixedSize(round(22 * s), round(22 * s))
        b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        b.setStyleSheet(f"""
            QPushButton {{ color: {FG_DIM}; background: transparent; border: none;
                           font-size: {max(9, round(13 * s))}px; border-radius: 4px; }}
            QPushButton:hover {{ color: #fafaf9; background: {HOVER_BG}; }}
        """)
        return b

    def commit_rename(self):
        """Save and close an open inline rename editor, if there is one.

        Called whenever the user clicks elsewhere, so renaming behaves like the
        rest of the app: click away = keep what you typed.
        """
        commit = self._active_rename_commit
        if commit is not None:
            commit()

    def mousePressEvent(self, e):
        # A click on blank sidebar space: finish any rename in progress.
        self.commit_rename()
        super().mousePressEvent(e)

    def target_parent(self) -> str:
        """Where a newly created item should go.

        The selected folder; if a journal is selected, its containing folder; and
        "root" when nothing is selected. Previously this was hardcoded to "root",
        so highlighting a folder had no effect on the + buttons.
        """
        node_id = self._selected_id or self._active_id
        node = self._library.find(node_id) if node_id else None
        if node is None:
            return "root"
        if node.is_folder:
            return node.id
        parent = self._library.root.parent_of(node.id)
        return parent.id if parent is not None else "root"

    # ── State from MainWindow ────────────────────────────────────────────────

    def set_active(self, node_id: str | None):
        """Highlight the open journal.

        Deliberately re-styles the EXISTING rows instead of calling
        `render_tree()`: rebuilding destroys the row the user is currently
        pressing, which killed drag-and-drop before it could start (the press
        landed, then the widget vanished before any mouse-move reached it).
        """
        if node_id == self._active_id:
            return
        self._active_id = node_id
        self._restyle_rows()

    def _restyle_rows(self):
        """Update highlight/dirty markers in place, keeping the widgets alive."""
        for row in self._tree_host.findChildren(_RowWidget):
            row.set_state(active=(row.node_id() == self._active_id),
                          dirty=(row.node_id() in self._dirty_ids),
                          drop_target=(row.node_id() == self._drop_target_id))

    def set_dirty_ids(self, dirty_ids: set[str]):
        """Journals with unsaved changes get a ● marker, like VSCode."""
        if dirty_ids != self._dirty_ids:
            self._dirty_ids = set(dirty_ids)
            self._restyle_rows()      # in place: never destroy a pressed row

    def apply_scale(self, scale: float):
        self._scale = scale
        self.setFixedWidth(round(self.BASE_W * scale))
        self.render_tree()

    # ── Rendering ────────────────────────────────────────────────────────────

    def render_tree(self):
        # Clear existing rows (keep the trailing stretch).
        #
        # `deleteLater()` alone defers destruction to the next event-loop pass,
        # so the old rows stay children of this widget until then — long enough
        # to be found by lookups and to be drawn alongside the new ones. Detach
        # them from the parent first so removal is immediate.
        while self._tree_layout.count() > 1:
            item = self._tree_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        rows: list[tuple[LibraryNode, int]] = []
        self._collect(self._library.root, -1, rows)

        for node, depth in rows:
            if node.id == self._renaming_id:
                self._tree_layout.insertWidget(
                    self._tree_layout.count() - 1, self._make_rename_row(node, depth)
                )
                continue
            row = _RowWidget(
                node, depth,
                active=(node.id == self._active_id),
                dirty=(node.id in self._dirty_ids),
                scale=self._scale,
                drop_target=(node.id == self._drop_target_id),
            )
            row.clicked.connect(self._on_row_clicked)
            row.double_clicked.connect(self._on_row_double_clicked)
            row.context_requested.connect(self._open_context_menu)
            self._tree_layout.insertWidget(self._tree_layout.count() - 1, row)

        if not rows:
            hint = QLabel("No journals yet.\nUse ＋ to create one.")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet(
                f"color: #57534e; font-size: {max(9, round(11 * self._scale))}px; "
                "background: transparent; padding: 16px;"
            )
            self._tree_layout.insertWidget(self._tree_layout.count() - 1, hint)

    def _collect(self, node: LibraryNode, depth: int,
                 out: list[tuple[LibraryNode, int]]):
        """Flatten the tree into visible rows (collapsed folders hide children).
        The invisible root contributes no row of its own."""
        if depth >= 0:
            out.append((node, depth))
            if node.is_folder and not node.expanded:
                return
        # Folders first, then journals — each group alphabetised, like VSCode.
        children = sorted(
            node.children, key=lambda c: (c.kind != FOLDER, c.name.lower())
        )
        for child in children:
            self._collect(child, depth + 1, out)

    # ── Row interactions ─────────────────────────────────────────────────────

    def _on_row_clicked(self, node_id: str):
        # Clicking a different row commits an open rename rather than discarding.
        if self._renaming_id is not None and self._renaming_id != node_id:
            self.commit_rename()
        node = self._library.find(node_id)
        if node is None:
            return
        self._selected_id = node_id
        if node.is_folder:
            self.folder_toggled.emit(node_id)
        else:
            self.journal_opened.emit(node_id)

    def _on_row_double_clicked(self, node_id: str):
        """Double-click renames, like a file explorer. A journal is already
        opened by the single click that precedes it."""
        self.begin_rename(node_id)

    # ── Inline rename ────────────────────────────────────────────────────────

    def begin_rename(self, node_id: str):
        self._renaming_id = node_id
        self.render_tree()

    def _make_rename_row(self, node: LibraryNode, depth: int) -> QWidget:
        s = self._scale
        wrap = QWidget()
        wrap.setFixedHeight(max(22, round(24 * s)))
        wrap.setStyleSheet(f"background: {ACTIVE_BG};")
        lay = QHBoxLayout(wrap)
        pad = round(6 * s) + depth * round(_RowWidget.INDENT * s)
        lay.setContentsMargins(pad, 0, round(6 * s), 0)

        edit = QLineEdit(node.name)
        edit.setStyleSheet(f"""
            QLineEdit {{ color: #fafaf9; background: #1c1917;
                         border: 1px solid {ACCENT}; border-radius: 3px;
                         font-size: {max(10, round(12 * s))}px; padding: 1px 4px; }}
        """)
        edit.selectAll()

        def commit():
            if self._renaming_id != node.id:
                return                      # already committed or cancelled
            name = edit.text().strip()
            self._renaming_id = None
            self._active_rename_commit = None
            if name and name != node.name:
                self.rename_requested.emit(node.id, name)
            else:
                self.render_tree()

        def cancel():
            self._renaming_id = None
            self._active_rename_commit = None
            self.render_tree()

        # `editingFinished` covers Enter and focus loss, but clicking blank
        # sidebar space moves focus nowhere, so it would never fire — the editor
        # just sat there. `_commit_rename()` is called from mousePressEvent (and
        # before any other row/panel interaction) to close that gap.
        self._active_rename_commit = commit
        edit.returnPressed.connect(commit)
        edit.editingFinished.connect(commit)
        # Escape cancels; QLineEdit has no dedicated signal for it.
        edit.keyPressEvent = self._rename_key_handler(edit, cancel)

        lay.addWidget(edit)
        QTimer.singleShot(0, edit.setFocus)
        return wrap

    @staticmethod
    def _rename_key_handler(edit: QLineEdit, cancel):
        original = QLineEdit.keyPressEvent

        def handler(e):
            if e.key() == Qt.Key.Key_Escape:
                # Detach the focus-loss commit before cancelling.
                edit.editingFinished.disconnect()
                cancel()
                return
            original(edit, e)
        return handler

    # ── Context menu (in-app, not an OS popup) ───────────────────────────────

    def _open_context_menu(self, node_id: str, global_pos):
        self.close_menu()
        node = self._library.find(node_id)
        if node is None:
            return

        window = self.window()
        menu = _ContextMenu(window, self._scale)
        parent_for_new = node.id if node.is_folder else "root"
        menu.add_item("New Journal",
                      lambda: self.new_journal_requested.emit(parent_for_new))
        menu.add_item("New Folder",
                      lambda: self.new_folder_requested.emit(parent_for_new))
        menu.add_separator()
        menu.add_item("Rename", lambda: self.begin_rename(node_id))
        menu.add_item("Delete", lambda: self.delete_requested.emit(node_id),
                      danger=True)
        menu.closed.connect(lambda: setattr(self, "_menu", None))
        menu.popup_at(window.mapFromGlobal(global_pos))
        self._menu = menu

    # ── Drag and drop ────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        """Handle drags that land on the scroll viewport / tree host.

        Those widgets sit between the rows and this panel; without forwarding,
        the viewport consumes the drag and no drop ever reaches us.
        """
        et = event.type()
        if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove,
                  QEvent.Type.Drop, QEvent.Type.DragLeave):
            if et == QEvent.Type.DragLeave:
                self.dragLeaveEvent(event)
                return True
            # Translate the position into this panel's coordinates.
            pos = obj.mapTo(self, event.position().toPoint())
            forwarded = _TranslatedDrag(event, pos)
            if et == QEvent.Type.DragEnter:
                self.dragEnterEvent(forwarded)
            elif et == QEvent.Type.DragMove:
                self.dragMoveEvent(forwarded)
            else:
                self.dropEvent(forwarded)
            if forwarded.is_accepted():
                event.acceptProposedAction()
            else:
                event.ignore()
            return True
        return super().eventFilter(obj, event)

    def _node_id_from(self, event) -> str | None:
        data = event.mimeData().data(_RowWidget.MIME)
        if data.isEmpty():
            return None
        return bytes(data).decode("utf-8")

    def _drop_parent_at(self, pos) -> str:
        """Which folder a drop at `pos` targets.

        A folder row takes the drop itself; a journal row means "the folder that
        journal lives in"; empty space below the tree means the top level.
        """
        child = self.childAt(pos)
        while child is not None and not isinstance(child, _RowWidget):
            child = child.parentWidget()
        if child is None:
            return "root"
        node = child._node
        if node.is_folder:
            return node.id
        parent = self._library.root.parent_of(node.id)
        return parent.id if parent is not None else "root"

    def dragEnterEvent(self, e):
        if self._node_id_from(e) is not None:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        node_id = self._node_id_from(e)
        if node_id is None:
            e.ignore()
            return
        parent_id = self._drop_parent_at(e.position().toPoint())
        # Don't highlight a target the move would be refused for.
        valid = (parent_id != node_id
                 and not self._library.is_ancestor(node_id, parent_id))
        highlight = parent_id if (valid and parent_id != "root") else None
        if highlight != self._drop_target_id:
            self._drop_target_id = highlight
            self._restyle_rows()
        if valid:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        if self._drop_target_id is not None:
            self._drop_target_id = None
            self._restyle_rows()
        super().dragLeaveEvent(e)

    def dropEvent(self, e):
        node_id = self._node_id_from(e)
        self._drop_target_id = None
        if node_id is None:
            e.ignore()
            return
        parent_id = self._drop_parent_at(e.position().toPoint())
        self.render_tree()
        self.move_requested.emit(node_id, parent_id)
        e.acceptProposedAction()

    def close_menu(self):
        if self._menu is not None:
            self._menu.dismiss()
            self._menu = None


class _ContextMenu(QWidget):
    """A lightweight in-app context menu: a full-window transparent hit-catcher
    with a small card, matching the app's no-OS-popup rule."""

    closed = pyqtSignal()

    def __init__(self, window: QWidget, scale: float):
        super().__init__(window)
        self._scale = scale
        self._closing = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(window.rect())

        self._card = QFrame(self)
        self._card.setObjectName("menuCard")
        self._card.setStyleSheet(f"""
            QFrame#menuCard {{ background: #292524;
                               border: 1px solid #44403c; border-radius: 6px; }}
        """)
        self._lay = QVBoxLayout(self._card)
        pad = round(4 * scale)
        self._lay.setContentsMargins(pad, pad, pad, pad)
        self._lay.setSpacing(0)
        self._width = round(150 * scale)

    def add_item(self, text: str, slot, danger: bool = False):
        s = self._scale
        b = QPushButton(text)
        b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        b.setFixedHeight(round(26 * s))
        color = "#fca5a5" if danger else FG
        hover = "#7f1d1d" if danger else "#3a3330"
        b.setStyleSheet(f"""
            QPushButton {{ color: {color}; background: transparent; border: none;
                           text-align: left; padding: 0 {round(10 * s)}px;
                           font-size: {max(10, round(12 * s))}px; border-radius: 4px; }}
            QPushButton:hover {{ background: {hover}; color: #fafaf9; }}
        """)

        def run():
            self.dismiss()
            slot()

        b.clicked.connect(run)
        self._lay.addWidget(b)

    def add_separator(self):
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: #44403c;")
        self._lay.addWidget(line)

    def popup_at(self, pos):
        self._card.setFixedWidth(self._width)
        self._card.adjustSize()
        x = min(pos.x(), self.width() - self._card.width() - 6)
        y = min(pos.y(), self.height() - self._card.height() - 6)
        self._card.move(max(6, x), max(6, y))
        self.show()
        self.raise_()

    def mousePressEvent(self, e):
        if not self._card.geometry().contains(e.pos()):
            self.dismiss()
        else:
            super().mousePressEvent(e)

    def dismiss(self):
        if self._closing:
            return
        self._closing = True
        self.closed.emit()
        self.hide()
        self.deleteLater()
