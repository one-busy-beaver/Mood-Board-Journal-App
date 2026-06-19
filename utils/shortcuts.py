"""
Central shortcut registry.

Action names are string constants defined here. DEFAULT_BINDINGS maps each
action to a key-binding string. ShortcutMap resolves those strings to
QKeySequence objects, handling Qt6's arrow-key quirk internally.

To support user-customisable bindings in the future, construct ShortcutMap
with an overrides dict (or call ShortcutMap.from_file) — no call-sites change.
"""

from PyQt6.QtCore import Qt, QKeyCombination
from PyQt6.QtGui import QKeySequence

# ── Action name constants ─────────────────────────────────────────────────────

SAVE             = "save"
NEW_NOTE         = "new_note"
DELETE           = "delete"
DELETE_ALT       = "delete_alt"       # secondary binding for the same action
REORDER_UP       = "reorder_up"
REORDER_DOWN     = "reorder_down"
REORDER_TO_FRONT = "reorder_to_front"
REORDER_TO_BACK  = "reorder_to_back"
OVERLAY_CONFIRM  = "overlay_confirm"  # confirm / close overlay
DISMISS          = "dismiss"          # cancel / close overlay

# ── Default bindings ──────────────────────────────────────────────────────────

DEFAULT_BINDINGS: dict[str, str] = {
    SAVE:             "Ctrl+S",
    NEW_NOTE:         "Ctrl+N",
    DELETE:           "Delete",
    DELETE_ALT:       "Backspace",
    REORDER_UP:       "Shift+Up",
    REORDER_DOWN:     "Shift+Down",
    REORDER_TO_FRONT: "Ctrl+Shift+Up",
    REORDER_TO_BACK:  "Ctrl+Shift+Down",
    OVERLAY_CONFIRM:  "Ctrl+Return",
    DISMISS:          "Escape",
}

# ── Key-sequence parser ───────────────────────────────────────────────────────

_ARROW_KEYS: dict[str, Qt.Key] = {
    "Up":    Qt.Key.Key_Up,
    "Down":  Qt.Key.Key_Down,
    "Left":  Qt.Key.Key_Left,
    "Right": Qt.Key.Key_Right,
}

_MODIFIERS: dict[str, Qt.KeyboardModifier] = {
    "Ctrl":  Qt.KeyboardModifier.ControlModifier,
    "Shift": Qt.KeyboardModifier.ShiftModifier,
    "Alt":   Qt.KeyboardModifier.AltModifier,
    "Meta":  Qt.KeyboardModifier.MetaModifier,
}


def parse_key_sequence(binding: str) -> QKeySequence:
    """Convert a binding string to QKeySequence.

    Arrow keys are handled via QKeyCombination to avoid Qt6's issue where
    QGraphicsView consumes arrow-key events before QShortcut sees them.
    All other bindings go through the standard QKeySequence string parser.
    """
    if not binding:
        return QKeySequence()

    parts = [p.strip() for p in binding.split("+")]
    key_name = parts[-1]

    if key_name in _ARROW_KEYS:
        mods = Qt.KeyboardModifier(0)
        for mod in parts[:-1]:
            mods |= _MODIFIERS.get(mod, Qt.KeyboardModifier(0))
        return QKeySequence(QKeyCombination(mods, _ARROW_KEYS[key_name]))

    return QKeySequence(binding)


# ── ShortcutMap ───────────────────────────────────────────────────────────────

class ShortcutMap:
    """Resolves action names to QKeySequence objects.

    Constructed with an optional overrides dict so future user-config loading
    requires no changes at call-sites::

        # Future: load from ~/.journal_app/keybindings.json
        shortcuts = ShortcutMap.from_file(config_path)
    """

    def __init__(self, overrides: dict[str, str] | None = None):
        self._bindings: dict[str, str] = {**DEFAULT_BINDINGS, **(overrides or {})}

    def key_sequence(self, action: str) -> QKeySequence:
        return parse_key_sequence(self._bindings.get(action, ""))

    def binding_str(self, action: str) -> str:
        """Human-readable string for display in tooltips / a keybindings UI."""
        return self._bindings.get(action, "")

    @classmethod
    def from_file(cls, path: str) -> "ShortcutMap":
        """Load user overrides from a JSON file (future use)."""
        import json
        with open(path, encoding="utf-8") as f:
            overrides = json.load(f)
        return cls(overrides)
