from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Board:
    title: str = "My Journal"
    notes: list = field(default_factory=list)   # list[Note]
    groups: list = field(default_factory=list)  # list[Group]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_saved: str = ""
