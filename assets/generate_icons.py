"""
Render the SVG tool icons in assets/icons/ to PNG.

Run once whenever an SVG changes:
    QT_QPA_PLATFORM=offscreen python assets/generate_icons.py

PNGs are what the app loads at runtime (raster = no QtSvg dependency needed).
"""

import os
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtCore import Qt
from PyQt6.QtSvg import QSvgRenderer

ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
SIZE = 48  # 2x for crispness on HiDPI


def render(svg_name: str):
    svg_path = os.path.join(ICONS_DIR, svg_name)
    png_path = os.path.splitext(svg_path)[0] + ".png"
    renderer = QSvgRenderer(svg_path)
    pm = QPixmap(SIZE, SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.save(png_path, "PNG")
    print(f"wrote {png_path}")


def main():
    app = QApplication(sys.argv)  # noqa: F841 — needed for QPixmap
    for name in os.listdir(ICONS_DIR):
        if name.endswith(".svg"):
            render(name)


if __name__ == "__main__":
    main()
