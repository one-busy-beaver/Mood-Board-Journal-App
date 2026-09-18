# Mood Board Journal App — Project Notes for Claude

## What this is
A desktop journal/mood-board app built with Python + PyQt6. A left **explorer**
sidebar holds a tree of folders and journals; each journal is its own blank
canvas of **sticky notes** the user can drag, resize, reorder, and edit. Journals
open as **VSCode-style tabs**. Saves under `~/.journal_app/`.

---

## Stack
- **Python 3.12+** (uses `str | None` union syntax, not `Optional`)
- **PyQt6** for all UI
- Run with `python main.py`

---

## Key architectural decisions

### Three-layer data model
```
Library            ~/.journal_app/library.json    folders + journals (structure only)
 └─ Journal        ~/.journal_app/journals/<id>.json   one canvas of notes
     └─ Note       sticky note (no title field)
```
- `Library`/`LibraryNode` (`models/library.py`) — the explorer tree. A node is a
  FOLDER (has `children`) or a JOURNAL (a leaf whose `id` names its file).
- `Journal` (`models/journal.py`) — what `Board` used to be. `models/board.py`
  still exports `Board = Journal` as a deprecated alias.
- Journals save to **separate files**, so Ctrl+S writes only the active journal.
- **Library structure saves immediately** (create/rename/delete/expand) — there
  is no natural "save the sidebar" gesture. Only *note* edits are explicit-save.
- A legacy single `board.json` is migrated into the first journal on first run
  and kept as `board.json.bak` (`PersistenceController._migrate_or_seed`).

### Tabs & sessions (`views/main_window.py`)
- `JournalSession` = one open journal: its own `BoardController`, `Workspace`,
  `dirty` flag, and `active_note_id`. Held in `MainWindow._sessions`.
- **Switching tabs never saves, prompts, or discards** — like VSCode, the other
  journal stays live in memory. Only *closing* a dirty tab prompts
  (`ConfirmOverlay`), and quitting with unsaved work prompts once.
- Pages live in a `QStackedWidget`; switching just changes the visible page.
- Per-journal `scale`: `MainWindow._scale` mirrors the active journal's.

### Window layout
The toolbar spans the **full window width**; the explorer sits *beneath* it in a
horizontal body row (`toolbar / [explorer | tabs+stack]`). Toggling the sidebar
therefore never shifts or resizes the toolbar.

### What is app-wide vs per-journal
The dividing line: **if it affects chrome shared by every journal, or belongs to
the user, it is app-wide** (`models/settings.py`, `settings.json`,
`SettingsController`). Only a journal's own content lives in its file.

| State | Where | Why |
|---|---|---|
| `scale` ("resolution") | **Settings** | zooms the toolbar, sidebar and tab bar — shared chrome. It was per-journal, which made switching tabs resize the whole window. |
| `saved_colors` | **Settings** | a colour saved in one journal must appear in all of them |
| notes, groups, title, timestamps | Journal | genuinely that journal's content |
| `Note.font_size`, `Note.color`, `Note.geometry` | Note | per-note by design |

Both app-wide settings save to disk **immediately** (like the library, unlike
note edits) — there is no "save settings" gesture.

`PersistenceController.load_settings` migrates each key **independently**: a
`settings.json` written before `scale` existed still picks it up, because a
missing *key* (not just a missing file) triggers that key's migration. Journals
may still contain stale `scale`/`saved_colors` keys; they are ignored on load and
dropped on the next save.

### Adaptive chrome (`utils/contrast.py`)
Anything drawn **on a note's colour** derives its own colour instead of
hardcoding a grey, so it stays readable on cream, pink, teal or near-black:
- `ink(bg)` → near-black or near-white, whichever contrasts better
- `muted_ink(bg)` → a softened version for secondary chrome (the overlay's
  "Note" caption, the × glyph) that is walked back toward full ink until it
  still clears 3:1, so "muted" can never become invisible
- `shade(bg, amount)` → tints toward black on light notes and toward white on
  dark ones (the old helper always multiplied toward black, so a dark note's
  title bar got darker instead of lighter)
- `blend(bg, toward, amount)` → generic mix

Decisions use **WCAG relative luminance**, not an RGB average: the eye weights
green far more than blue, so `(r+g+b)/3` misjudges saturated colours. The old
hardcoded `#78716c` failed 3:1 on 6 of 11 representative notes (1.01:1 on the
saved teal — effectively invisible); every colour now clears the floor.

**Ceiling worth knowing:** on mid-luminance backgrounds neither near-black nor
near-white reaches 4.5:1 (e.g. #6E74BF tops out ~4.1:1). That is a property of
the colour, not a bug; `ink()` always picks the better of the two.

Covered by `scratchpad/contrast_check.py` (maths, incl. 20k random colours) and
`scratchpad/adaptive.py` (the real widgets).

### Colour panel (`views/color_panel.py`) — one page, Colors-app style
- **No tabs.** Mode bar on top swaps only the picker surface; the saved-colour
  strip is pinned underneath it, so the palette is visible while you pick.
- Three modes in `views/widgets/color_pickers.py`, all sharing HSV state:
  **Disc** (hue ring + inscribed SV square), **Classic** (SV rectangle + hue and
  brightness sliders), **Value** (H/S/B + R/G/B sliders with readouts).
- **Colour-maths contract** (see that module's docstring): every picker stores
  HSV in 0..1 and uses the *same* mapping forward (paint) and inverse (hit-test),
  so marker position, swatch and hex can never disagree. Hue runs clockwise from
  12 o'clock: `x = cx + r·sin(2πh)`, `y = cy − r·cos(2πh)`, inverse
  `h = atan2(dx, −dy)/2π`. SV planes are rendered per-pixel via
  `QColor.fromHsvF` rather than approximated with gradients. Greys report
  hue −1 from `getHsvF()`; pickers keep the previous hue instead of snapping to
  red. Verified: 309/309 exact hex round-trips per mode.
- **The palette is GLOBAL** (`models/settings.py` + `SettingsController`), not
  per-journal — a colour saved in one journal appears in all of them. Palette
  edits write to disk immediately (like the library, unlike note edits).
  `Journal.saved_colors` is legacy; the old per-journal lists are merged into
  settings.json on first run.

### Explorer (`views/explorer_panel.py`)
- VSCode-like tree: nested folders, click a journal to open, click a folder to
  expand/collapse, inline rename, right-click context menu (in-app, never an OS
  popup). Folders sort before journals, each alphabetised.
- Emits **intent signals only**; all mutation goes through `LibraryController`.
- **Single click** selects (and opens a journal / toggles a folder);
  **double click renames** inline, like a file explorer.
- **New items go into the selected folder**, via `target_parent()`: the selected
  folder, or the folder containing the selected journal, else "root". The header
  ＋ buttons used to hardcode "root", so highlighting a folder did nothing.
- **Drag and drop** re-parents: rows start a `QDrag` past the drag threshold (so
  a plain click still selects), the panel highlights a valid drop folder in
  amber, and dropping on a journal row targets that journal's folder. Invalid
  drops are refused by `Library.move` — a node cannot land in itself or in its
  own subtree, which would detach the tree.
  Two things this depends on, both easy to break:
  1. **The scroll viewport must accept drops.** Rows live inside the
     `QScrollArea`, so enabling `setAcceptDrops` on the panel alone let the
     viewport swallow every drag. The viewport and tree host accept drops and
     forward them via `eventFilter` (`_TranslatedDrag` remaps coordinates).
  2. **Rows must survive a press.** `set_active`/`set_dirty_ids` re-style rows
     **in place** (`_restyle_rows`) instead of calling `render_tree()`. Clicking
     a journal opens it → `set_active` → a rebuild used to destroy the very row
     under the cursor, so no mouse-move ever reached it and a drag could never
     begin.
- **Rename commits on click-away.** `editingFinished` alone was not enough:
  clicking blank sidebar space moves focus nowhere, so it never fired and the
  editor just sat open. `commit_rename()` is called from the panel's
  `mousePressEvent`, when another row is clicked, and from MainWindow when a note
  or the canvas is clicked. Escape still discards.
- `render_tree` detaches old rows with `setParent(None)` before `deleteLater()`:
  deferred deletion alone left stale rows parented until the next event-loop
  pass, so a renamed row could briefly appear twice.
- Dirty journals show a ● marker, as does their tab.

### MVC split
- **Models** are plain dataclasses, no Qt. Serialized to/from JSON by `PersistenceController`.
- **Controllers** inherit `QObject`, own state, emit Qt signals.
- **Views** connect to controller signals; never mutate models directly.

### Two in-app surface types (neither is ever an OS popup)
**`BaseOverlay(QWidget)`** — modal, full-window, dims the board:
- Takes a `parent.grab()` snapshot before showing, draws it dimmed in `paintEvent`
- Centered card (`QFrame`) with drop shadow
- Escape closes (via `ShortcutMap`), click outside card closes
- Subclasses implement: `_populate_card(layout)`, `_card_background()`,
  `_initial_focus()`, `_on_close()`
- Current subclass: `NoteOverlay` (the enlarged note editor)

**`BasePanel(QWidget)`** (`views/base_panel.py`) — non-modal anchored popover:
- Same subclass hooks as `BaseOverlay`, but **no dimming/snapshot** — the board
  stays live. Transparent full-window hit-catcher; click outside or Esc closes.
- `_reposition_card()` anchors the card under an `anchor` widget (a toolbar
  button), clamped inside the window. GoodNotes/Notability-style tool popover.
- Current subclass: `ColorPanel`. Use this for future tool popovers; use
  `BaseOverlay` only for genuinely modal, focus-stealing UI.

### Shortcut system (`utils/shortcuts.py`)
- All action names are string constants (`SAVE`, `NEW_NOTE`, `REORDER_UP`, etc.)
- `DEFAULT_BINDINGS` dict maps action → binding string in one place
- `ShortcutMap` resolves strings to `QKeySequence` via `parse_key_sequence()`
- Arrow keys are handled via `QKeyCombination` internally (a Qt6 compatibility
  detail retained by the shortcut map)
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
  the active note's color; opens `ColorPanel` anchored under its own button via
  `window.open_color_picker_for_active(anchor=self._button)`. Disabled when no
  note is active.
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
- **Note overlay edits are a draft**: `NoteOverlay` commits to the model on
  **Ctrl+S** (`_save`) or Ctrl+Return (`_confirm` = save + close). There is no
  Done button. The close glyph doubles as the dirty indicator — an amber ● while
  unsaved, reverting to × on hover — the same affordance the explorer and tab bar
  use. Closing while dirty raises a Save / Don't Save / Cancel prompt rather than
  discarding silently.
  Note this commits to the **in-memory** model only; the journal still reaches
  disk through its own explicit save.
  The nested prompt registers itself as `MainWindow._active_overlay` via
  `NoteOverlay.dialog_opened`, so the app knows a modal is up and hands control
  back to the editor when it closes.
- **Ctrl+S is routed, not duplicated.** `MainWindow._save()` forwards to
  `overlay._save()` whenever an overlay is open. Do NOT give the overlay its own
  `QShortcut` for Ctrl+S: a window-scoped shortcut always beats one inside an
  overlay, and two enabled shortcuts for the same key are *ambiguous* — Qt fires
  NEITHER, which is exactly how Ctrl+S ended up doing nothing at all. An event
  filter does not help either, since shortcuts resolve before key events reach
  widgets. Ctrl+Return is unique to the overlay, so a plain QShortcut is fine
  there.
- **Colour edits are a draft too**: `ColorPanel` previews live on the note (so you
  can judge it in context) but records `_original_color` on open and restores it in
  `_on_close()` unless **Apply** was pressed. `_set_draft()` = preview,
  `_apply_current()` = commit (also emits `color_applied(hex)` so future targets
  besides notes can be routed from `MainWindow`). **Save** only touches the
  palette, never the note.

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

### Selection frame (`views/widgets/selection_frame.py`)
- The blue outline, 8 resize handles (corner dots + edge capsules) and the
  rotation knob live in ONE widget that covers the whole workspace and is always
  raised last. **The note stays at its own depth; only the chrome is on top**, so
  handles are never buried by an overlapping note.
- **The frame is sized to the chrome it draws** (`_fit_to_content`: the rotated
  handle bounds plus the rotation stem), NOT to the whole workspace. A
  workspace-sized frame became the widget under *every* click — it forwarded them
  on, but that put one selected note in the path of all input. Its own
  coordinates are local, so `_hit`, the gesture handlers and
  `_forward_to_workspace` translate by `self._origin`.
- **Never call `grabMouse()`.** Two separate app-wide input freezes came from it:
  an explicit grab routes every mouse event in the application to one widget and
  is only released by a mouse-release delivered to that same widget. If the
  gesture ends any other way — the cursor leaves, a dialog opens, the widget is
  hidden (a rotated note hides its real widget!) — the grab survives and every
  click in the app dies. Qt's *implicit* grab already delivers a drag to whoever
  accepted the press, which is all this needs. `scratchpad/nograb.py` guards this
  statically and at runtime.
- `SelectionFrame.cancel_gesture()` / `Workspace.cancel_gestures()` abandon any
  half-finished drag; `MainWindow` calls them before showing an overlay and
  before quitting, so a stray gesture can never block a dialog.
- Resizing happens in the note's LOCAL (unrotated) space, then the centre offset
  is rotated back — otherwise the anchored edge drifts on a rotated note.

### Rotation
- `NoteGeometry.rotation` (degrees clockwise about the centre) persists.
- **Qt cannot rotate a live QWidget** — there is no `setRotation`. A rotated note
  therefore hides its real widget and `Workspace.paintEvent` draws it from a
  `grab()` snapshot, transformed about its centre. This costs nothing here: notes
  are read-only display cards and editing happens in the unrotated zoom view.
  (The alternative — `QGraphicsView` + `QGraphicsProxyWidget` — would mean
  reverting the workspace rewrite of commit `4b39e90`.)
- Rotated notes get no mouse events of their own, so `Workspace` hit-tests them
  via `NoteWindow.contains_scene_point` (inverse rotation, then a plain rect
  test) and drives their drag through `begin_external_drag`/`drag_to`.
- Shift while dragging the knob snaps to 15°.

### Double-click routing
A note's editor opens on double-click, but the note itself only receives the
event when it has a live widget on top. Two cases route through
`Workspace.mouseDoubleClickEvent` instead, which hit-tests and calls
`expand_requested` on the note it finds:
  - the note is **selected** — the selection frame is over it and forwards down
  - the note is **rotated** — it is painted from a snapshot and has no live
    widget at all
The workspace used to `return` silently in that branch, so double-clicking a
selected or rotated note did nothing. `scratchpad/dbl.py` covers all seven
paths (empty canvas, note selected/unselected × rotated/unrotated, and a handle,
which must do nothing).

### Creation gestures (on empty workspace only)
- single click → deselect only
- double-click → a note at the default size, centred on the cursor
- click-drag → a note of exactly the dragged size, with a live preview rectangle.
  Drags under `DRAG_IGNORE` (20px in both axes) create nothing; larger drags
  clamp up to the minimum note size (140×110).

### Sticky notes (`views/note_window.py`) — NO title bar
- A note is a bare coloured card: **no title bar, no expand/close buttons**.
- Drag from **anywhere** on the body. Resizing is NOT on the note — see the
  selection frame.
- The card body is **read-only** (`WA_TransparentForMouseEvents`) so the sticky
  behaves as one solid object rather than a text box in a frame.
- **Double-click is the only way to edit** — it opens `NoteOverlay` (the zoomed
  view, unchanged). Single click just selects/raises.
- Selection is shown by the **`SelectionFrame`** (see above), not by the note's
  own border. Clicking empty canvas deselects: `Workspace.background_clicked`
  → `MainWindow._on_background_clicked` detaches the frame, clears the active
  note, and disables note-scoped tools.
- **The note itself is never raised** — not on click, not during a drag. The
  frame carries the highlight on top instead.
- Hovering a note shows a **move cursor** (`SizeAllCursor`): the whole card is a
  drag handle. An unselected note shows NO resize cursor, because it is not
  resizable — resizing is only offered through the selection frame's handles.
- `Note.title` was **deleted** — it was cosmetic-only. Don't reintroduce it.
- Notes are clamped into view by `Workspace.ensure_in_bounds()` on resize/scale;
  there is no pan, so an off-edge note would otherwise be unreachable.

### Z-ordering
- `Note.geometry.z_index` is the persistent stacking value, and it is the ONLY
  thing that decides what is on top.
- **Clicking a note does NOT raise it** — not visually, not in the model.
  An earlier "visual-only `raise_()`" on click was removed: because nothing ever
  restored the saved order, the screen drifted permanently out of sync with
  `z_index` and looked exactly like click-to-raise had changed the layer.
- A note is lifted (`NoteWindow._lift`) **only while being dragged or resized**,
  so it isn't hidden behind neighbours mid-move, then `_drop()` calls
  `Workspace.restack()` on release to snap back to the saved order.
- Only explicit shortcuts change z permanently (Shift+Up/Down, Ctrl+Shift+Up/Down).
- `BoardController.z_order_changed` → `Workspace.restack()` re-applies persistent
  order (sort by `z_index`, `raise_()` bottom→top). Called once after load too.

### Text size vs. "resolution" (two SEPARATE, non-composing concepts)
- **Per-note font size** (`Note.font_size`, pt) — the ONLY thing that changes body
  text size. Set via the toolbar `FontSizeTool` for the active note.
  `update_font_size` → `note_font_changed` → `NoteWindow.apply_font`
  (`QFont("Georgia", note.font_size)` — no scale factor).
- **Global scale / "resolution"** (`Settings.scale`, `Ctrl+=` / `Ctrl+-` / `Ctrl+0`) —
  a UI zoom like changing display scaling. It scales **the toolbar** (panel height,
  icons, buttons, captions, brand — `MainWindow._px` + `_rebuild_toolbar` on
  `scale_changed`) **and each note's box geometry + title-bar chrome**. It does
  **NOT** touch body text.
- **Note geometry is stored in the model as base (scale-1.0) coords.** A
  `NoteWindow` renders at `base × scale` (`_relayout`); drag/resize happen in
  screen pixels and are divided back to base in `emit_geometry`. Create positions
  are converted screen→base in `MainWindow._add_note_center` / `_on_create_at`.
- `font_size` persists with its journal; `scale` persists in `settings.json`.

### Active note tracking
- `MainWindow._active_note_id` — set whenever any part of a note is interacted
  with (via `bring_to_front_requested` signal)
- Used by reorder shortcuts + the color tool to know which note to act on
- Reorder/delete shortcuts defer to text editing via `_editing_text()` (a text
  field having focus means Delete/Shift+Up etc. edit text instead of the note)
- Cleared when that note is deleted

---

## Implemented features
- [x] Explorer sidebar (Ctrl+B) — folder/journal tree, nested folders, inline
      rename, right-click menu, delete with confirmation
- [x] Multiple journals, each its own blank canvas, open as VSCode-style tabs
      (Ctrl+Shift+N new journal, Ctrl+W close tab)
- [x] Sticky notes with no title bar; double-click body to edit in the zoom view
- [x] Selection frame with 8 resize handles + rotation knob, always on top
- [x] Note rotation (any angle, Shift snaps to 15°), persisted
- [x] Double-click to create; click-drag on empty space to create at that size
- [x] Bounded workspace (dot-grid); notes are draggable/resizable in-app windows
- [x] Create notes (double-click empty workspace or Ctrl+N or toolbar button)
- [x] Drag notes from anywhere on the card; resize and rotate with the
      selection frame
- [x] Stacking follows `z_index` only; notes lift during a drag and snap back
- [x] Per-note font size (toolbar Font stepper) — the only control of body text size
- [x] App-wide "resolution" zoom (Ctrl+= / - / 0): scales toolbar, sidebar, tab
      bar + note boxes, NOT body text. One value for the whole app (persisted in
      settings.json), applied to every open journal at once.
- [x] Read-only card bodies with a focused overlay editor on double-click
- [x] Note overlay editor (full-screen dimmed overlay, same color as card)
- [x] Color panel (`views/color_panel.py`) — anchored popover, one page with a
      **Disc / Classic / Value** mode bar and the saved-colour strip pinned
      below the picker. Two adjacent actions: **Save** (→ global palette) and
      **Apply** (→ the note). The **Save** button reflects whether the *current*
      colour is already in the palette ("Saved ✓", disabled) and re-enables as
      soon as the colour changes.
- [x] Global colour palette shared by every journal (`settings.json`)
- [x] Saved swatches (`views/widgets/swatch_grid.py`) — left-aligned, wrap at 6
      per row, new colors append to the right. **Absolutely positioned, no
      QLayout**: a dragged chip floats freely while the others animate into their
      new slots (iOS-home-screen style live gap) via `QPropertyAnimation` on
      `pos`. Right-click opens a centered Delete confirm (click away to cancel).
- [x] Z-order reordering: Shift+Up/Down (one step), Ctrl+Shift+Up/Down (front/back)
- [x] Delete active note (Delete / Backspace, when not editing text)
- [x] Explicit save only (Ctrl+S / Save button) with a dirty indicator; overlay
      Ctrl+S commits the editor draft to the in-memory journal, while closing a
      dirty draft offers Save / Don't Save / Cancel
- [x] Persist the library to `~/.journal_app/library.json` and each journal to
      `~/.journal_app/journals/<id>.json`
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

- `note_popup.py` was deleted (it referenced the removed `Note.title`).
- `NoteController` (`controllers/note_controller.py`) is underused — note-view
  signals go directly to `BoardController`. Don't remove it; it may be needed
  when templates have per-note logic.
- `models/group.py` exists but groups have no UI yet.
- No `__init__.py` files — Python 3.3+ namespace packages.
- Sticky notes have NO title bar and NO per-note buttons. Delete is
  Delete/Backspace on the active note; color is a top-toolbar tool.
- **Color tool lives in the top toolbar**, not on individual notes — see the
  "Toolbar tool system" section. Kept in sync via `_refresh_tools()`.
- `Workspace` is a bounded QWidget rather than the old `BoardCanvas` graphics
  view. Keep its direct mouse routing in sync with the selection frame and
  rotated-note hit testing.
- Toolbar tools use the `MainWindow._make_tool(widget, name)` pattern: a control
  with a small caption underneath. Reuse it when adding new toolbar tools.
