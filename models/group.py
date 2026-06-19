from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Group:
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = "Group"
    note_ids: list = field(default_factory=list)
    color: str = "#E0E7FF"
