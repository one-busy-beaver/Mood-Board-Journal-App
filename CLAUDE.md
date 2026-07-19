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

### Toolbar tool system (`views/tools/`)
- `Tool` base class (`views/tools/base_tool.py`): each tool builds its own toolbar
  widget via `create_control(window)` and updates itself via `refresh(window)`.
  The default `create_control` is an icon button that runs `activate(window)`
  (button-tools also use `is_enabled` / `style_button`); tools needing a richer
  control override `create_control` + `refresh`.
- Tools are registered in `MainWindow.__init__`
  (`self._tools = [ColorTool(), FontSizeTool()]`). The toolbar wraps each tool's
  control with a caption; `_refresh_tools()` calls `tool.refresh(self)` whenever
  app state changes (note focus, color/font change, delete).
- Tool controls size themselves off `window.ui_scale()`; the whole toolbar is
  rebuilt (`_rebuild_toolbar`) when the global scale changes.
- `ColorTool` (`color_tool.py`): paint-bucket icon whose bottom-border stripe shows
  the active note's color; opens `ColorPickerOverlay` via
  `window.open_color_picker_for_active()`. Disabled when no note is active.
- `FontSizeTool` (`font_size_tool.py`): −/value/+ stepper editing the **active
  note's** `font_size` (per-note) via `window.change_active_font(±1)`.
- Tools call back into `MainWindow`'s public interface: `active_note()`,
  `open_color_picker_for_active()`, `change_active_font()`. Add new tools by
  subclassing `Tool` and appending to `self._tools`.
- Icons live in `assets/icons/` as SVG; `assets/generate_icons.py` renders them to
  PNG (raster = no runtime QtSvg dependency). Re-run it when an SVG changes:
  `QT_QPA_PLATFORM=offscreen python assets/generate_icons.py`.

### Save model — explicit save only
- **Nothing persists to disk except an explicit Save** (Ctrl+S / Save button).
  There is NO autosave and NO save-on-close (closing discards unsaved changes).
- In-memory model still updates live (inline card typing, color, geometry) so the
  UI stays consistent — but that's the working copy, not disk.
- `BoardController.board_changed` → `MainWindow._on_board_changed` sets `_dirty`
  and shows a "● Unsaved" / "Saved ✓" indicator in the toolbar status area.
- **Note overlay edits are a draft**: `NoteOverlay` commits title+content to the
  model only via `_confirm()` (Done button / Ctrl+Return). Closing via ×, Escape,
  or click-outside discards. (Color picker still applies live — it's preview-driven.)

### Template system (`models/content.py`)
- `CONTENT_REGISTRY: dict[str, type[NoteContent]]` maps `template_type` string → class
- `Note.template_type` determines which content class is used
- Currently only `"plain_text"` → `PlainTextContent`
- Adding a new template = new `NoteContent` subclass + register in `CONTENT_REGISTRY`
  + new view class in `views/templates/`

### Workspace & note windows (`views/workspace.py`, `views/note_window.py`)
- **No infinite canvas.** `Workspace(QWidget)` is a bounded, dot-grid container
  filling the area under the toolbar. There is NO zoom/pan of a plane.
- Each note is a `NoteWindow(QFrame)` — an in-app "OS window": drag by the title
  bar, resize from any edge/corner (via a `RESIZE_MARGIN` border on the frame),
  raise on interaction. Positioned absolutely with `move()`/`setGeometry()`;
  never in a layout.
- `NoteWindow` emits the same signals the old `NoteItem` did
  (`removed`, `expand_requested`, `geometry_changed`, `content_changed`,
  `bring_to_front_requested`), so `MainWindow` wiring is view-agnostic.
- Double-clicking empty workspace → `create_note_requested` (children consume
  their own clicks, so this only fires on empty space).

### Z-ordering
- `Note.geometry.z_index` is the persistent stacking value.
- **Click-to-raise is visual only**: clicking/focusing a note calls `raise_()`
  (immediate feel of OS windows) but does NOT change `z_index`.
- Only explicit shortcuts change z permanently (Shift+Up/Down, Ctrl+Shift+Up/Down).
- `BoardController.z_order_changed` → `Workspace.restack()` re-applies persistent
  order (sort by `z_index`, `raise_()` bottom→top). Called once after load too.

### Text size vs. "resolution" (two SEPARATE, non-composing concepts)
- **Per-note font size** (`Note.font_size`, pt) — the ONLY thing that changes body
  text size. Set via the toolbar `FontSizeTool` for the active note.
  `update_font_size` → `note_font_changed` → `NoteWindow.apply_font`
  (`QFont("Georgia", note.font_size)` — no scale factor).
- **Global scale / "resolution"** (`Board.scale`, `Ctrl+=` / `Ctrl+-` / `Ctrl+0`) —
  a UI zoom like changing display scaling. It scales **the toolbar** (panel height,
  icons, buttons, captions, brand — `MainWindow._px` + `_rebuild_toolbar` on
  `scale_changed`) **and each note's box geometry + title-bar chrome**. It does
  **NOT** touch body text.
- **Note geometry is stored in the model as base (scale-1.0) coords.** A
  `NoteWindow` renders at `base × scale` (`_relayout`); drag/resize happen in
  screen pixels and are divided back to base in `emit_geometry`. Create positions
  are converted screen→base in `MainWindow._add_note_center` / `_on_create_at`.
- Both `font_size` and `scale` persist in `board.json`.

### Active note tracking
- `MainWindow._active_note_id` — set whenever any part of a note is interacted
  with (via `bring_to_front_requested` signal)
- Used by reorder shortcuts + the color tool to know which note to act on
- Reorder/delete shortcuts defer to text editing via `_editing_text()` (a text
  field having focus means Delete/Shift+Up etc. edit text instead of the note)
- Cleared when that note is deleted

---

## Implemented features
- [x] Bounded workspace (dot-grid); notes are draggable/resizable in-app windows
- [x] Create notes (double-click empty workspace or Ctrl+N or toolbar button)
- [x] Drag notes by title bar; resize from any edge/corner
- [x] Click-to-raise (visual); persistent z only via reorder shortcuts
- [x] Per-note font size (toolbar Font stepper) — the only control of body text size
- [x] Global "resolution" zoom (Ctrl+= / - / 0): scales panel + note boxes/chrome,
      NOT body text (persisted)
- [x] Inline text editing in card body
- [x] Note overlay editor (full-screen dimmed overlay, same color as card)
- [x] Note background color picker (36-swatch palette + custom color), opened from
      a top-toolbar color tool that acts on the active note
- [x] Z-order reordering: Shift+Up/Down (one step), Ctrl+Shift+Up/Down (front/back)
- [x] Delete active note (Delete / Backspace, when not editing text)
- [x] Explicit save only (Ctrl+S / Save button) with a dirty indicator; note
      overlay edits commit only on Done (× / Esc / outside discard)
- [x] Persist to `~/.journal_app/board.json`
- [x] Modular toolbar tools (`views/tools/`); color tool acts on the active note
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
- Each note card's title bar has 2 buttons (expand ✏ | close ×). Button positions
  are computed in `NoteItem` using `BTN_SIZE=14`, `BTN_PAD=6`. There is NO per-note
  color button — color is a top-toolbar tool (see below).
- **Color tool lives in the top toolbar**, not on individual notes — see the
  "Toolbar tool system" section. Kept in sync via `_refresh_tools()`.
- `BoardCanvas.keyPressEvent` deliberately ignores all four arrow keys so they
  reach `MainWindow`'s shortcuts instead of scrolling the view.
- **Wheel routing**: `BoardCanvas.wheelEvent` first checks the topmost note under
  the cursor via `_note_under_cursor` and calls `NoteItem.try_wheel_scroll(delta)`.
  If that note's editor can scroll in the wheel direction it consumes the event
  (scrolls the note); only at the editor's top/bottom edge — or over empty canvas —
  does the wheel fall through to canvas zoom. `_note_under_cursor` resolves
  proxy/handle child items up to their owning note by duck-typing
  `try_wheel_scroll`, keeping the view decoupled from `NoteItem`.
- Toolbar tools use the `MainWindow._make_tool(widget, name)` pattern: a control
  with a small caption underneath. Reuse it when adding new toolbar tools.
