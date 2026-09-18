"""Owns app-wide settings: the shared colour palette and the UI scale.

Both are global. A colour saved while editing one journal is available in every
journal, and the scale ("resolution") zooms shared chrome — toolbar, sidebar, tab
bar — so it cannot sensibly differ per journal. Like the library (and unlike note
edits), these are written to disk immediately; there is no "save settings"
gesture.
"""

from PyQt6.QtCore import QObject, pyqtSignal

from models.settings import Settings


class SettingsController(QObject):
    saved_colors_changed = pyqtSignal()
    scale_changed = pyqtSignal(float)        # app-wide UI zoom

    SCALE_MIN = 0.5
    SCALE_MAX = 3.0

    def __init__(self, settings: Settings, persistence):
        super().__init__()
        self._settings = settings
        self._persistence = persistence

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def saved_colors(self) -> list:
        return self._settings.saved_colors

    def is_saved(self, color: str) -> bool:
        key = color.upper()
        return any(c.upper() == key for c in self._settings.saved_colors)

    def save_color(self, color: str):
        """Add a colour to the palette. No duplicates; new colours go to the end
        so they appear to the right of existing swatches."""
        color = color.upper()
        if self.is_saved(color):
            return
        self._settings.saved_colors.append(color)
        self._commit()

    def move_saved_color(self, color: str, new_index: int):
        """Reorder the palette (drag-and-drop on the swatch strip)."""
        colors = self._settings.saved_colors
        try:
            old = next(i for i, c in enumerate(colors) if c.upper() == color.upper())
        except StopIteration:
            return
        new_index = max(0, min(len(colors) - 1, new_index))
        if new_index == old:
            return
        colors.insert(new_index, colors.pop(old))
        self._commit()

    def remove_saved_color(self, color: str):
        before = len(self._settings.saved_colors)
        self._settings.saved_colors = [
            c for c in self._settings.saved_colors if c.upper() != color.upper()
        ]
        if len(self._settings.saved_colors) != before:
            self._commit()

    # ── UI scale ("resolution") ──────────────────────────────────────────────

    @property
    def scale(self) -> float:
        return self._settings.scale

    def set_scale(self, scale: float):
        scale = max(self.SCALE_MIN, min(self.SCALE_MAX, scale))
        if abs(scale - self._settings.scale) < 1e-6:
            return
        self._settings.scale = scale
        self._persistence.save_settings(self._settings)
        self.scale_changed.emit(scale)

    def nudge_scale(self, direction: int):
        """direction > 0 = larger, < 0 = smaller. Multiplicative step."""
        factor = 1.1 if direction > 0 else 1 / 1.1
        self.set_scale(self._settings.scale * factor)

    def reset_scale(self):
        self.set_scale(1.0)

    def _commit(self):
        self._persistence.save_settings(self._settings)
        self.saved_colors_changed.emit()
