"""The journal library: a VSCode-style tree of folders and journals.

The library holds *structure only* — names, nesting, order, and which journal
each leaf points at. A journal's actual notes live in its own file
(`journals/<id>.json`) so journals save independently of one another.

Node kinds:
  - FOLDER   — has `children`, no journal payload
  - JOURNAL  — a leaf pointing at a journal file by its own `id`
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

FOLDER = "folder"
JOURNAL = "journal"


@dataclass
class LibraryNode:
    id: str = field(default_factory=lambda: str(uuid4()))
    kind: str = JOURNAL
    name: str = "Untitled"
    children: list = field(default_factory=list)  # list[LibraryNode], folders only
    expanded: bool = True                         # folder disclosure state
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_folder(self) -> bool:
        return self.kind == FOLDER

    def walk(self):
        """Yield this node and every descendant, depth-first."""
        yield self
        for child in self.children:
            yield from child.walk()

    def find(self, node_id: str) -> "LibraryNode | None":
        return next((n for n in self.walk() if n.id == node_id), None)

    def parent_of(self, node_id: str) -> "LibraryNode | None":
        for node in self.walk():
            if any(c.id == node_id for c in node.children):
                return node
        return None

    def remove(self, node_id: str) -> bool:
        parent = self.parent_of(node_id)
        if parent is None:
            return False
        parent.children = [c for c in parent.children if c.id != node_id]
        return True


@dataclass
class Library:
    """Root of the tree. The root itself is an invisible folder — its children
    are what the explorer renders at the top level."""
    root: LibraryNode = field(
        default_factory=lambda: LibraryNode(kind=FOLDER, name="", id="root")
    )

    def journals(self) -> list[LibraryNode]:
        return [n for n in self.root.walk() if n.kind == JOURNAL]

    def find(self, node_id: str) -> LibraryNode | None:
        return self.root.find(node_id)

    def add(self, node: LibraryNode, parent_id: str | None = None):
        """Add `node` under `parent_id` (or at the top level). Falls back to the
        top level if the target isn't a folder."""
        parent = self.root if parent_id in (None, "root") else self.root.find(parent_id)
        if parent is None or not parent.is_folder:
            parent = self.root
        parent.children.append(node)

    def is_ancestor(self, node_id: str, maybe_descendant_id: str) -> bool:
        """True if `maybe_descendant_id` is inside the subtree of `node_id`."""
        node = self.root.find(node_id)
        if node is None:
            return False
        return any(n.id == maybe_descendant_id for n in node.walk())

    def move(self, node_id: str, new_parent_id: str, index: int | None = None) -> bool:
        """Re-parent `node_id` under `new_parent_id`.

        Refuses moves that would detach the tree: a node cannot be dropped into
        itself or into one of its own descendants (that would orphan the whole
        subtree), and only folders can receive children.
        """
        if node_id == new_parent_id or node_id == "root":
            return False
        node = self.root.find(node_id)
        if node is None:
            return False
        target = (self.root if new_parent_id in (None, "root")
                  else self.root.find(new_parent_id))
        if target is None or not target.is_folder:
            return False
        if self.is_ancestor(node_id, target.id):
            return False          # would put a folder inside its own subtree

        current_parent = self.root.parent_of(node_id)
        if current_parent is None:
            return False
        if current_parent.id == target.id:
            return False          # already there; nothing to do

        current_parent.children = [c for c in current_parent.children
                                   if c.id != node_id]
        if index is None or index < 0 or index > len(target.children):
            target.children.append(node)
        else:
            target.children.insert(index, node)
        return True

    def remove(self, node_id: str) -> list[str]:
        """Remove a node (and its subtree). Returns the ids of every journal
        removed, so their files can be deleted too."""
        node = self.root.find(node_id)
        if node is None:
            return []
        journal_ids = [n.id for n in node.walk() if n.kind == JOURNAL]
        self.root.remove(node_id)
        return journal_ids
