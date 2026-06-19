from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QColorDialog,
)
from PyQt6.QtGui import QColor, QFont

from controllers.board_controller import BoardController
from utils.shortcuts import ShortcutMap
from views.base_overlay import BaseOverlay


PALETTE = [
    # Warm — yellows, creams, oranges
    "#FFFBEB", "#FEF3C7", "#FDE68A", "#FFEDD5", "#FED7AA", "#FCA5A5",
    # Warm — pinks, roses
    "#FDF2F8", "#FBCFE8", "#F9A8D4", "#FCE7F3", "#FECDD3", "#FDA4AF",
    # Cool — blues
    "#EFF6FF", "#DBEAFE", "#BFDBFE", "#E0F2FE", "#BAE6FD", "#7DD3FC",
    # Cool — greens, teals
    "#F0FDF4", "#D1FAE5", "#A7F3D0", "#ECFDF5", "#BAE6FD", "#6EE7B7",
    # Purples, lavenders
    "#FAF5FF", "#EDE9FE", "#DDD6FE", "#F3E8FF", "#E9D5FF", "#C4B5FD",
    # Neutrals — light to dark
    "#FAFAF9", "#F5F5F4", "#E7E5E4", "#D6D3D1", "#78716C", "#1C1917",
]

SWATCH_SIZE   = 38
SWATCH_GAP    = 8
COLS          = 6


class ColorPickerOverlay(BaseOverlay):
    CARD_W = 380
    CARD_H = 390

    def __init__(self, note_id: str, current_color: str,
                 board_ctrl: BoardController, parent, shortcuts: ShortcutMap):
        self._note_id       = note_id
        self._current_color = current_color
        self._board_ctrl    = board_ctrl
        self._swatches: dict[str, QPushButton] = {}
        super().__init__(parent, shortcuts)

    # ── BaseOverlay hooks ─────────────────────────────────────────────────────

    def _card_background(self) -> str:
        return "#fafaf9"

    def _populate_card(self, layout: QVBoxLayout):
        # ── Header ──
        header = QWidget()
        header.setFixedHeight(50)
        header.setStyleSheet("""
            QWidget {
                background: #f5f5f4;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 12, 0)

        lbl = QLabel("Note Color")
        lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        lbl.setStyleSheet("color: #44403c; background: transparent;")
        hl.addWidget(lbl)
        hl.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(26, 26)
        close_btn.setFlat(True)
        close_btn.setStyleSheet("""
            QPushButton { color: #78716c; font-size: 20px; font-weight: bold;
                          background: transparent; border: none; padding: 0; }
            QPushButton:hover { color: #1c1917; }
        """)
        close_btn.clicked.connect(self._close)
        hl.addWidget(close_btn)
        layout.addWidget(header)

        # ── Divider ──
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet("background: #e7e5e4; border: none;")
        layout.addWidget(div)

        # ── Swatch grid ──
        grid_wrap = QWidget()
        grid_wrap.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_wrap)
        grid.setContentsMargins(20, 18, 20, 14)
        grid.setSpacing(SWATCH_GAP)

        for i, color in enumerate(PALETTE):
            btn = QPushButton()
            btn.setFixedSize(SWATCH_SIZE, SWATCH_SIZE)
            btn.setToolTip(color)
            self._swatches[color] = btn
            self._style_swatch(btn, color)
            btn.clicked.connect(lambda _, c=color: self._pick(c))
            grid.addWidget(btn, i // COLS, i % COLS)

        layout.addWidget(grid_wrap)

        # ── Footer ──
        footer = QWidget()
        footer.setStyleSheet("background: transparent;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 4, 20, 18)

        custom_btn = QPushButton("Custom color…")
        custom_btn.setFixedHeight(30)
        custom_btn.setStyleSheet("""
            QPushButton { color: #78716c; background: transparent;
                          border: 1px solid #d6d3d1; border-radius: 6px;
                          font-size: 12px; padding: 0 12px; }
            QPushButton:hover { background: #f5f5f4; color: #44403c; }
        """)
        custom_btn.clicked.connect(self._pick_custom)
        fl.addWidget(custom_btn)
        fl.addStretch()

        done_btn = QPushButton("Done")
        done_btn.setFixedSize(80, 30)
        done_btn.setStyleSheet("""
            QPushButton { background: #f59e0b; color: white; border: none;
                          border-radius: 6px; font-size: 12px; font-weight: 600; }
            QPushButton:hover { background: #d97706; }
            QPushButton:pressed { background: #b45309; }
        """)
        done_btn.clicked.connect(self._close)
        fl.addWidget(done_btn)
        layout.addWidget(footer)

    # ── Swatch helpers ────────────────────────────────────────────────────────

    def _style_swatch(self, btn: QPushButton, color: str):
        selected = color.lower() == self._current_color.lower()
        ring = "#3b82f6" if selected else "transparent"
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                border-radius: 6px;
                border: 2.5px solid {ring};
            }}
            QPushButton:hover {{ border: 2.5px solid #a8a29e; }}
        """)

    def _pick(self, color: str):
        old = self._current_color
        self._current_color = color
        if old in self._swatches:
            self._style_swatch(self._swatches[old], old)
        if color in self._swatches:
            self._style_swatch(self._swatches[color], color)
        self._board_ctrl.update_color(self._note_id, color)

    def _pick_custom(self):
        chosen = QColorDialog.getColor(
            QColor(self._current_color), self, "Custom Color"
        )
        if chosen.isValid():
            hex_color = chosen.name()
            # Register the swatch slot if it's in palette, otherwise just apply
            self._current_color = hex_color
            self._board_ctrl.update_color(self._note_id, hex_color)
            # Deselect all palette swatches since it's a custom color
            for c, btn in self._swatches.items():
                self._style_swatch(btn, c)
