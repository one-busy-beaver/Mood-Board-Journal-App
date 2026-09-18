"""App-wide settings, shared by every journal.

Anything that belongs to the *user* or to the application as a whole — rather
than to one journal's contents — lives here:

  saved_colors  the colour palette; a colour saved in one journal is available
                in all of them
  scale         the UI "resolution" zoom. It scales the toolbar, sidebar, tab bar
                and note boxes, i.e. chrome shared by every journal, so it is one
                application-wide setting rather than a per-journal one.
"""

from dataclasses import dataclass, field


@dataclass
class Settings:
    saved_colors: list = field(default_factory=list)  # list[str] hex, global
    scale: float = 1.0                                # global UI zoom
