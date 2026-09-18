"""VSCode-style tab strip for open journals.

Open journals stay open when you switch — switching never prompts and never
discards. A dirty tab shows a ● instead of its × until hovered; closing a dirty
tab is what triggers the save prompt (handled by MainWindow).
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor

BG = "#141211"
TAB_BG = "#1f1d1b"
TAB_ACTIVE_BG = "#292524"
FG = "#d6d3d1"
FG_DIM = "#78716c"
ACCENT = "#f59e0b"


class _Tab(QWidget):
    selected = pyqtSignal(str)
    close_clicked = pyqtSignal(str)

    def __init__(self, node_id: str, name: str, active: bool, dirty: bool,
                 scale: float, parent=None):
        super().__init__(parent)
        self._id = node_id
        self._dirty = dirty
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(round(32 * scale))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bg = TAB_ACTIVE_BG if active else TAB_BG
        top = f"border-top: 2px solid {ACCENT};" if active else "border-top: 2px solid transparent;"
        self.setStyleSheet(
            f"_Tab {{ background: {bg}; {top} border-right: 1px solid #141211; }}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(round(10 * scale), 0, round(6 * scale), 0)
        lay.setSpacing(round(6 * scale))

        label = QLabel(name)
        label.setStyleSheet(
            f"color: {FG if active else FG_DIM}; background: transparent; "
            f"font-size: {max(10, round(12 * scale))}px;"
        )
        lay.addWidget(label)

        self._close = QPushButton("●" if dirty else "✕")
        self._close.setToolTip("Close journal")
        self._close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._close.setFixedSize(round(16 * scale), round(16 * scale))
        self._close.setStyleSheet(f"""
            QPushButton {{ color: {ACCENT if dirty else FG_DIM}; background: transparent;
                           border: none; font-size: {max(8, round(10 * scale))}px; }}
            QPushButton:hover {{ color: #fafaf9; background: #44403c; border-radius: 3px; }}
        """)
        self._close.clicked.connect(lambda: self.close_clicked.emit(self._id))
        lay.addWidget(self._close)

    def enterEvent(self, e):
        if self._dirty:
            self._close.setText("✕")  # reveal the close affordance on hover
        super().enterEvent(e)

    def leaveEvent(self, e):
        if self._dirty:
            self._close.setText("●")
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._id)
            e.accept()
            return
        super().mousePressEvent(e)


class TabBar(QWidget):
    tab_selected = pyqtSignal(str)
    tab_close_requested = pyqtSignal(str)

    def __init__(self, scale: float = 1.0, parent=None):
        super().__init__(parent)
        self._scale = scale
        self.setStyleSheet(f"background: {BG};")
        self.setFixedHeight(round(34 * scale))

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG}; border: none; }}
            QScrollBar:horizontal {{ height: 0; }}
        """)
        self._host = QWidget()
        self._host.setStyleSheet(f"background: {BG};")
        self._lay = QHBoxLayout(self._host)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        self._lay.addStretch()
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll)

    def apply_scale(self, scale: float):
        self._scale = scale
        self.setFixedHeight(round(34 * scale))

    def render_tabs(self, tabs: list[tuple[str, str, bool]], active_id: str | None):
        """tabs: list of (node_id, name, dirty), in open order."""
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for node_id, name, dirty in tabs:
            tab = _Tab(node_id, name, node_id == active_id, dirty, self._scale)
            tab.selected.connect(self.tab_selected)
            tab.close_clicked.connect(self.tab_close_requested)
            self._lay.insertWidget(self._lay.count() - 1, tab)
