import json
import os
from models.board import Board
from models.note import Note, NoteGeometry
from models.group import Group

SAVE_PATH = os.path.join(os.path.expanduser("~"), ".journal_app", "board.json")


class PersistenceController:
    def load(self) -> Board:
        if not os.path.exists(SAVE_PATH):
            return Board()
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                return self._deserialize(json.load(f))
        except Exception:
            return Board()

    def save(self, board: Board):
        os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(self._serialize(board), f, indent=2, ensure_ascii=False)

    def _serialize(self, board: Board) -> dict:
        return {
            "title": board.title,
            "created_at": board.created_at,
            "scale": board.scale,
            "notes": [self._serialize_note(n) for n in board.notes],
            "groups": [
                {"id": g.id, "name": g.name, "note_ids": g.note_ids, "color": g.color}
                for g in board.groups
            ],
        }

    def _serialize_note(self, note: Note) -> dict:
        g = note.geometry
        return {
            "id": note.id,
            "title": note.title,
            "template_type": note.template_type,
            "content": note.content,
            "color": note.color,
            "font_size": note.font_size,
            "group_id": note.group_id,
            "geometry": {
                "x": g.x, "y": g.y,
                "width": g.width, "height": g.height,
                "z_index": g.z_index,
            },
        }

    def _deserialize(self, data: dict) -> Board:
        board = Board(
            title=data.get("title", "My Journal"),
            created_at=data.get("created_at", ""),
            scale=data.get("scale", 1.0),
        )
        for nd in data.get("notes", []):
            geo = nd.get("geometry", {})
            board.notes.append(Note(
                id=nd["id"],
                title=nd.get("title", "Note"),
                template_type=nd.get("template_type", "plain_text"),
                content=nd.get("content", {}),
                color=nd.get("color", "#FFFBEB"),
                font_size=nd.get("font_size", 10),
                group_id=nd.get("group_id"),
                geometry=NoteGeometry(
                    x=geo.get("x", 100), y=geo.get("y", 100),
                    width=geo.get("width", 240), height=geo.get("height", 200),
                    z_index=geo.get("z_index", 0),
                ),
            ))
        for gd in data.get("groups", []):
            board.groups.append(Group(
                id=gd["id"], name=gd.get("name", ""),
                note_ids=gd.get("note_ids", []),
                color=gd.get("color", "#E0E7FF"),
            ))
        self._normalize_positions(board)
        return board

    # Migration: pre-workspace saves used infinite-canvas scene coordinates that
    # could be negative. The bounded workspace has no negative space, so shift the
    # whole board back into view — preserving relative layout — when any note sits
    # off the top/left. No-op for boards already in positive space.
    MARGIN = 40

    def _normalize_positions(self, board: Board):
        if not board.notes:
            return
        min_x = min(n.geometry.x for n in board.notes)
        min_y = min(n.geometry.y for n in board.notes)
        dx = (self.MARGIN - min_x) if min_x < 0 else 0
        dy = (self.MARGIN - min_y) if min_y < 0 else 0
        if dx == 0 and dy == 0:
            return
        for n in board.notes:
            n.geometry.x += dx
            n.geometry.y += dy
