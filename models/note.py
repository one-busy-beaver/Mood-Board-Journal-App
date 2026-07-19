from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class NoteGeometry:
    x: float = 100.0
    y: float = 100.0
    width: float = 240.0
    height: float = 200.0
    z_index: float = 0.0


@dataclass
class Note:
    id: str = field(default_factory=lambda: str(uuid4()))
    geometry: NoteGeometry = field(default_factory=NoteGeometry)
    template_type: str = "plain_text"
    content: dict = field(default_factory=dict)
    group_id: str | None = None
    color: str = "#FFFBEB"
    title: str = "Note"
    font_size: int = 10   # per-note body font size (pt); global scale multiplies it
