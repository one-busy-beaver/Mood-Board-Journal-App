"""Owns the journal library tree (folders + journals) and emits Qt signals when
it changes. Mirrors BoardController's role, one level up: BoardController owns
the notes *inside* one journal, LibraryController owns which journals exist.

The library is structure-only, and structural edits (create/rename/delete/
expand) are written to disk immediately — they are not part of the per-journal
explicit-save model, since there is no natural "save the sidebar" gesture.
"""

from PyQt6.QtCore import QObject, pyqtSignal

from models.library import Library, LibraryNode, FOLDER, JOURNAL


class LibraryController(QObject):
    library_changed = pyqtSignal()                # tree structure changed
    journal_deleted = pyqtSignal(str, list)       # node_id, removed journal ids
    node_created = pyqtSignal(object)             # LibraryNode

    def __init__(self, library: Library, persistence):
        super().__init__()
        self._library = library
        self._persistence = persistence

    @property
    def library(self) -> Library:
        return self._library

    def find(self, node_id: str) -> LibraryNode | None:
        return self._library.find(node_id)

    def name_of(self, node_id: str) -> str:
        node = self._library.find(node_id)
        return node.name if node else "Untitled"

    # ── Mutations ────────────────────────────────────────────────────────────

    def create_journal(self, parent_id: str = "root",
                       name: str = "Untitled Journal") -> LibraryNode:
        node = LibraryNode(kind=JOURNAL, name=self._unique_name(parent_id, name))
        self._library.add(node, parent_id)
        self._expand(parent_id)
        self._commit()
        self.node_created.emit(node)
        return node

    def create_folder(self, parent_id: str = "root",
                      name: str = "New Folder") -> LibraryNode:
        node = LibraryNode(kind=FOLDER, name=self._unique_name(parent_id, name))
        self._library.add(node, parent_id)
        self._expand(parent_id)
        self._commit()
        self.node_created.emit(node)
        return node

    def rename(self, node_id: str, name: str):
        node = self._library.find(node_id)
        name = name.strip()
        if node is None or not name or node.name == name:
            return
        node.name = name
        self._commit()

    def delete(self, node_id: str):
        """Remove a node and its subtree. Journal files are deleted too — this is
        the one genuinely destructive library action, so callers confirm first."""
        removed = self._library.remove(node_id)
        if removed or self._library.find(node_id) is None:
            self._persistence.delete_journal_files(removed)
            self._commit()
            self.journal_deleted.emit(node_id, removed)

    def move(self, node_id: str, new_parent_id: str) -> bool:
        """Re-parent a node (drag-and-drop in the explorer). Returns whether the
        move actually happened, so the caller can ignore invalid drops."""
        if not self._library.move(node_id, new_parent_id):
            return False
        node = self._library.find(node_id)
        # Keep sibling names unique after the move, as creation does.
        if node is not None:
            siblings = [c for c in (self._library.find(new_parent_id)
                                    or self._library.root).children
                        if c.id != node_id]
            if any(c.name == node.name for c in siblings):
                node.name = self._unique_name(new_parent_id, node.name)
        self._expand(new_parent_id)
        self._commit()
        return True

    def toggle_folder(self, node_id: str):
        node = self._library.find(node_id)
        if node is not None and node.is_folder:
            node.expanded = not node.expanded
            self._commit()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _expand(self, parent_id: str):
        parent = self._library.find(parent_id)
        if parent is not None and parent.is_folder:
            parent.expanded = True

    def _unique_name(self, parent_id: str, name: str) -> str:
        """Avoid two identically-named siblings (they'd be indistinguishable in
        the explorer). Appends ' 2', ' 3', … like a file manager."""
        parent = self._library.find(parent_id) or self._library.root
        existing = {c.name for c in parent.children}
        if name not in existing:
            return name
        n = 2
        while f"{name} {n}" in existing:
            n += 1
        return f"{name} {n}"

    def _commit(self):
        self._persistence.save_library(self._library)
        self.library_changed.emit()
