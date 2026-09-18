"""Disk layout (all under ~/.journal_app/):

    library.json          the folder/journal tree (structure only)
    settings.json         app-wide user settings (colour palette + UI scale)
    journals/<id>.json    one file per journal (its notes, colors, scale)
    board.json            LEGACY single-board save; migrated on first run

Journals save independently, so an explicit Save only writes the journal you
edited. Nothing here is called automatically — persistence is explicit-save only.
"""

import json
import os
import shutil
from datetime import datetime

from models.journal import Journal
from models.note import Note, NoteGeometry
from models.group import Group
from models.library import Library, LibraryNode, FOLDER, JOURNAL
from models.settings import Settings

APP_DIR = os.path.join(os.path.expanduser("~"), ".journal_app")
LIBRARY_PATH = os.path.join(APP_DIR, "library.json")
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
JOURNALS_DIR = os.path.join(APP_DIR, "journals")
LEGACY_BOARD_PATH = os.path.join(APP_DIR, "board.json")


class PersistenceController:

    # ── Library ──────────────────────────────────────────────────────────────

    def load_library(self) -> Library:
        if not os.path.exists(LIBRARY_PATH):
            return self._migrate_or_seed()
        try:
            with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            root = self._node_from_dict(data.get("root", {}))
            root.id = "root"
            root.kind = FOLDER
            return Library(root=root)
        except Exception:
            return self._migrate_or_seed()

    def save_library(self, library: Library):
        os.makedirs(APP_DIR, exist_ok=True)
        with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
            json.dump({"root": self._node_to_dict(library.root)}, f,
                      indent=2, ensure_ascii=False)

    def _node_to_dict(self, node: LibraryNode) -> dict:
        return {
            "id": node.id,
            "kind": node.kind,
            "name": node.name,
            "expanded": node.expanded,
            "created_at": node.created_at,
            "children": [self._node_to_dict(c) for c in node.children],
        }

    def _node_from_dict(self, data: dict) -> LibraryNode:
        node = LibraryNode(
            id=data.get("id") or LibraryNode().id,
            kind=data.get("kind", JOURNAL),
            name=data.get("name", "Untitled"),
            expanded=data.get("expanded", True),
            created_at=data.get("created_at", ""),
        )
        node.children = [self._node_from_dict(c) for c in data.get("children", [])]
        return node

    # ── Settings (app-wide, shared by every journal) ─────────────────────────

    def load_settings(self, library: Library | None = None) -> Settings:
        """Load global settings, lifting anything still stored per journal.

        `saved_colors` and `scale` both used to live on each journal even though
        they are application-wide (a colour saved in one was invisible in the
        others; the scale zooms shared chrome). Each key migrates INDEPENDENTLY:
        settings.json written before `scale` existed must still pick it up, so a
        missing key — not just a missing file — triggers that key's migration."""
        data: dict = {}
        if os.path.exists(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}  # unreadable — rebuild from the journals

        have_colors = "saved_colors" in data
        have_scale = "scale" in data
        settings = Settings(
            saved_colors=list(data.get("saved_colors", [])),
            scale=float(data.get("scale", 1.0)),
        )
        if have_colors and have_scale:
            return settings

        if library is not None:
            seen: set[str] = {c.upper() for c in settings.saved_colors}
            scale = None
            for node in library.journals():
                path = self.journal_path(node.id)
                if not os.path.exists(path):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        jdata = json.load(f)
                    if not have_colors:
                        for color in jdata.get("saved_colors", []):
                            key = str(color).upper()
                            if key not in seen:
                                seen.add(key)
                                settings.saved_colors.append(color)
                    # `scale` used to be stored per journal even though it scales
                    # shared chrome; adopt the first one found as the app-wide value.
                    if not have_scale and scale is None and "scale" in jdata:
                        scale = float(jdata["scale"])
                except Exception:
                    continue  # skip an unreadable journal, keep the rest
            if scale is not None:
                settings.scale = scale
        self.save_settings(settings)
        return settings

    def save_settings(self, settings: Settings):
        os.makedirs(APP_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump({"saved_colors": list(settings.saved_colors),
                       "scale": settings.scale}, f, indent=2, ensure_ascii=False)

    # ── Journals ─────────────────────────────────────────────────────────────

    def journal_path(self, journal_id: str) -> str:
        return os.path.join(JOURNALS_DIR, f"{journal_id}.json")

    def load_journal(self, journal_id: str, title: str = "Untitled") -> Journal:
        path = self.journal_path(journal_id)
        if not os.path.exists(path):
            return Journal(id=journal_id, title=title)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return self._deserialize_journal(json.load(f), journal_id, title)
        except Exception:
            return Journal(id=journal_id, title=title)

    def save_journal(self, journal: Journal):
        os.makedirs(JOURNALS_DIR, exist_ok=True)
        journal.last_saved = datetime.now().isoformat()
        with open(self.journal_path(journal.id), "w", encoding="utf-8") as f:
            json.dump(self._serialize_journal(journal), f, indent=2,
                      ensure_ascii=False)

    def delete_journal_files(self, journal_ids: list[str]):
        for jid in journal_ids:
            try:
                os.remove(self.journal_path(jid))
            except OSError:
                pass  # already gone / never saved — nothing to clean up

    def _serialize_journal(self, journal: Journal) -> dict:
        return {
            "id": journal.id,
            "title": journal.title,
            "created_at": journal.created_at,
            "last_saved": journal.last_saved,
            "notes": [self._serialize_note(n) for n in journal.notes],
            "groups": [
                {"id": g.id, "name": g.name, "note_ids": g.note_ids, "color": g.color}
                for g in journal.groups
            ],
        }

    def _serialize_note(self, note: Note) -> dict:
        g = note.geometry
        return {
            "id": note.id,
            "template_type": note.template_type,
            "content": note.content,
            "color": note.color,
            "font_size": note.font_size,
            "group_id": note.group_id,
            "geometry": {
                "x": g.x, "y": g.y,
                "width": g.width, "height": g.height,
                "z_index": g.z_index,
                "rotation": g.rotation,
            },
        }

    def _deserialize_journal(self, data: dict, journal_id: str,
                             title: str) -> Journal:
        journal = Journal(
            id=journal_id,
            title=data.get("title", title),
            created_at=data.get("created_at", ""),
            last_saved=data.get("last_saved", ""),
        )
        for nd in data.get("notes", []):
            geo = nd.get("geometry", {})
            journal.notes.append(Note(
                id=nd["id"],
                template_type=nd.get("template_type", "plain_text"),
                content=nd.get("content", {}),
                color=nd.get("color", "#FFFBEB"),
                font_size=nd.get("font_size", 10),
                group_id=nd.get("group_id"),
                geometry=NoteGeometry(
                    x=geo.get("x", 100), y=geo.get("y", 100),
                    width=geo.get("width", 240), height=geo.get("height", 200),
                    z_index=geo.get("z_index", 0),
                    rotation=geo.get("rotation", 0.0),
                ),
            ))
        for gd in data.get("groups", []):
            journal.groups.append(Group(
                id=gd["id"], name=gd.get("name", ""),
                note_ids=gd.get("note_ids", []),
                color=gd.get("color", "#E0E7FF"),
            ))
        self._normalize_positions(journal)
        return journal

    # ── Migration ────────────────────────────────────────────────────────────

    def _migrate_or_seed(self) -> Library:
        """First run under the library layout. If a legacy board.json exists,
        turn it into the first journal (preserving its notes) instead of starting
        empty; otherwise seed one blank journal."""
        library = Library()
        node = LibraryNode(kind=JOURNAL, name="My Journal")

        if os.path.exists(LEGACY_BOARD_PATH):
            try:
                with open(LEGACY_BOARD_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                node.name = data.get("title") or "My Journal"
                journal = self._deserialize_journal(data, node.id, node.name)
                self.save_journal(journal)
                # Keep the original as a backup rather than deleting user data.
                shutil.move(LEGACY_BOARD_PATH, LEGACY_BOARD_PATH + ".bak")
            except Exception:
                pass  # unreadable legacy file — fall through to a blank journal

        library.add(node)
        self.save_library(library)
        return library

    # Migration: pre-workspace saves used infinite-canvas scene coordinates that
    # could be negative. The bounded workspace has no negative space, so shift the
    # whole journal back into view — preserving relative layout — when any note
    # sits off the top/left. No-op for journals already in positive space.
    MARGIN = 40

    def _normalize_positions(self, journal: Journal):
        if not journal.notes:
            return
        min_x = min(n.geometry.x for n in journal.notes)
        min_y = min(n.geometry.y for n in journal.notes)
        dx = (self.MARGIN - min_x) if min_x < 0 else 0
        dy = (self.MARGIN - min_y) if min_y < 0 else 0
        if dx == 0 and dy == 0:
            return
        for n in journal.notes:
            n.geometry.x += dx
            n.geometry.y += dy
