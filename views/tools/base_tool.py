"""
Modular toolbar tool.

A Tool bundles everything the toolbar needs to render and run one action:
its display name, tooltip, an optional icon asset, an enabled-state rule, and
the action itself. Today `activate()` opens an overlay; a future sidebar variant
can override it without changing the toolbar. New tools subclass Tool and are
added to MainWindow's tool list.
"""

import os

from PyQt6.QtGui import QIcon

_ICONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets", "icons",
)


def icon_path(filename: str) -> str:
    return os.path.join(_ICONS_DIR, filename)


class Tool:
    name: str = ""           # caption shown under the button
    tooltip: str = ""        # hover text
    icon_file: str | None = None  # filename in assets/icons/, or None

    def icon(self) -> QIcon:
        if not self.icon_file:
            return QIcon()
        return QIcon(icon_path(self.icon_file))

    def is_enabled(self, window) -> bool:
        """Whether the tool can be used in the current app state."""
        return True

    def style_button(self, button, window) -> None:
        """Hook for dynamic per-state button styling (e.g. a color stripe).
        Called whenever the toolbar refreshes."""
        pass

    def activate(self, window) -> None:
        """Run the tool. Default pattern: open an overlay on `window`."""
        raise NotImplementedError
