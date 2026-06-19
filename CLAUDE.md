# Mood Board Journal App — Project Notes for Claude

## What this is
A desktop journal/mood-board app built with Python + PyQt6. Notes are free-floating cards on an infinite canvas. The user can drag, resize, reorder, and edit them. Saves to `~/.journal_app/board.json`.

---

## Stack
- **Python 3.12+** (uses `str | None` union syntax, not `Optional`)
- **PyQt6** for all UI
- Run with `python main.py`

---

## Key architectural decisions

### MVC split
- **Models** are plain dataclasses, no Qt. Serialized to/from JSON by `PersistenceController`.
- **Controllers** inherit `QObject`, own state, emit Qt signals.
- **Views** connect to controller signals; never mutate models directly.

### Overlay system (`BaseOverlay`)
All "modal panel" UI uses `BaseOverlay(QWidget)`:
- Takes a `parent.grab()` snapshot before showing, draws it dimmed in `paintEvent`
- Centered card (`QFrame`) with drop shadow
- Escape closes (via `ShortcutMap`), click outside card closes
- Subclasses implement: `_populate_card(layout)`, `_card_background()`,
  `_initial_focus()`, `_on_close()`
- Current subclasses: `NoteOverlay`, `ColorPickerOverlay`
- Future subclasses (templates, settings, etc.) should extend `BaseOverlay` too

### Shortcut system (`utils/shortcuts.py`)
- All action names are string constants (`SAVE`, `NEW_NOTE`, `REORDER_UP`, etc.)
- `DEFAULT_BINDINGS` dict maps action → binding string in one place
- `ShortcutMap` resolves strings to `QKeySequence` via `parse_key_sequence()`
- Arrow keys handled via `QKeyCombination` internally (Qt6 quirk — `QGraphicsView`
  swallows arrow keys before `QShortcut` sees them; `BoardCanvas.keyPressEvent`
  also ignores arrow keys to let them propagate)
- Created once in `main.py`, passed to `MainWindow`, then to overlays
- **Future user keybindings**: load JSON overrides → `ShortcutMap(overrides=...)`
  or `ShortcutMap.from_file(path)` — no call-site changes needed

### Template system (`models/content.py`)
- `CONTENT_REGISTRY: dict[str, type[NoteContent]]` maps `template_type` string → class
- `Note.template_type` determines which content class is used
- Currently only `"plain_text"` → `PlainTextContent`
- Adding a new template = new `NoteContent` subclass + register in `CONTENT_REGISTRY`
  + new view class in `views/templates/`

### Z-ordering
- `Note.geometry.z_index` is the persistent stacking value
- Dragging a note temporarily boosts its visual z by +10000, restores on mouse release
- Only explicit shortcuts change z permanently (Shift+Up/Down, Ctrl+Shift+Up/Down)
- `BoardController.z_order_changed` signal updates `NoteItem.setZValue()`

### Active note tracking
- `MainWindow._active_note_id` — set whenever any part of a note is clicked
  (via `bring_to_front_requested` signal)
- Used by reorder shortcuts to know which note to act on
- Cleared when that note is deleted

---

## Implemented features
- [x] Infinite canvas with zoom (scroll wheel) and pan (middle mouse)
- [x] Create notes (double-click canvas or Ctrl+N or toolbar button)
- [x] Drag notes by title bar (visual z-boost during drag, no permanent z change)
- [x] Resize notes (8-direction handles, appear on selection)
- [x] Inline text editing in card body
- [x] Note overlay editor (full-screen dimmed overlay, same color as card)
- [x] Note background color picker (36-swatch palette + custom color)
- [x] Z-order reordering: Shift+Up/Down (one step), Ctrl+Shift+Up/Down (front/back)
- [x] Delete selected note (Delete / Backspace)
- [x] Autosave every 60s + save on close + Ctrl+S
- [x] Persist to `~/.journal_app/board.json`
- [x] Decoupled shortcut system (central registry, user-customizable in future)

---

## Planned features (not yet implemented)

### Near term
- [ ] **Rich text** — switch `PlainTextTemplate` → `RichTextTemplate` (QTextEdit with
      HTML body). Add formatting toolbar (bold/italic/underline, text color, font, size).
      `PlainTextContent.body` would become HTML. Do this BEFORE adding new templates
      since all dated templates will want rich text too.
- [ ] **Template selector UI** — picker shown when creating a note (or changeable
      in the overlay). Needed before adding more template types.

### Dated templates
All share the same extensibility hook (`CONTENT_REGISTRY` + new view in `views/templates/`).
Implement in this order:

- [ ] **Dated daily** — `DailyContent(date, body)`. View: date header (locked) +
      rich-text body.
- [ ] **Dated weekly** — `WeeklyContent(week_start, cells: dict[str, str])`.
      View: configurable grid or timeline layout; Mon vs Sun start.
- [ ] **Dated monthly** — `MonthlyContent(year, month, cells: dict[str, str])`.
      View: calendar grid; configurable week start day.

### Long term
- [ ] **Custom template builder** — drag-and-drop field composer.
      Needs `models/template_def.py` (field specs, layout config) +
      `views/templates/builder.py`. Implement after all built-in templates are done.
- [ ] **User keybindings** — load `~/.journal_app/keybindings.json` into
      `ShortcutMap(overrides=...)` in `main.py`. Add a keybindings settings overlay.
- [ ] **Groups** — `Group` model exists but has no UI yet.
- [ ] **Multiple board/views** — not yet planned in detail.

---

## Things to know before touching the code

- `note_popup.py` is dead code (superseded by `NoteOverlay`) but kept intentionally.
- `NoteController` (`controllers/note_controller.py`) is underused — `NoteItem`
  signals go directly to `BoardController`. Don't remove it; it may be needed when
  templates have per-note logic.
- `models/group.py` exists but groups have no UI yet.
- No `__init__.py` files — Python 3.3+ namespace packages.
- The color swatch in each note card's title bar is the leftmost of 3 buttons
  (color ● | expand ✏ | close ×). Button positions are computed in `NoteItem`
  using `BTN_SIZE=14`, `BTN_PAD=6`.
- `BoardCanvas.keyPressEvent` deliberately ignores all four arrow keys so they
  reach `MainWindow`'s shortcuts instead of scrolling the view.
