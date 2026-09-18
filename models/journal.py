from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Journal:
    """One canvas worth of sticky notes. Was `Board` before the library refactor;
    a journal is now one leaf of the library tree, stored in its own file.

    Holds only what genuinely belongs to THIS journal. The UI scale and the
    colour palette are application-wide and live in `models/settings.py`.
    """
    id: str = ""
    title: str = "Untitled"
    notes: list = field(default_factory=list)   # list[Note]
    groups: list = field(default_factory=list)  # list[Group]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_saved: str = ""
