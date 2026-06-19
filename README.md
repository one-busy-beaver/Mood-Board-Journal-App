# Mood-Board-Journal-App

A desktop journal / mood-board app where notes are free-floating cards on an
infinite canvas. Built with Python + PyQt6.

## Features

- **Infinite canvas** with scroll-wheel zoom and middle-mouse pan
- **Notes** you can create (double-click, `Ctrl+N`, or the toolbar), drag, resize,
  and edit inline
- **Expanded editor** — open any note in a full-screen dimmed overlay
- **Color tool** in the top toolbar that recolors the active note (36-swatch
  palette + custom color)
- **Z-order control** — `Shift+Up/Down` to nudge, `Ctrl+Shift+Up/Down` for
  front/back
- **Explicit save** (`Ctrl+S`) with an unsaved-changes indicator; overlay edits
  commit only when you click **Done**
- Board persists to `~/.journal_app/board.json`

## Run

```bash
python main.py
```

Requires Python 3.12+ and PyQt6.

## Architecture

MVC split — plain dataclass models, `QObject` controllers that emit signals, and
PyQt6 views. See [CLAUDE.md](CLAUDE.md) for the full architecture, design
decisions, and roadmap.
