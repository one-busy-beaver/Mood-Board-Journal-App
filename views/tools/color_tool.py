"""Color tool: paint-bucket button whose bottom stripe shows the active note's
color. Opens the color picker overlay for the active note."""

from views.tools.base_tool import Tool


class ColorTool(Tool):
    name = "Color"
    tooltip = "change color"
    icon_file = "color_bucket.png"

    def is_enabled(self, window) -> bool:
        return window.active_note() is not None

    def style_button(self, button, window) -> None:
        note = window.active_note()
        stripe = max(2, round(4 * window.ui_scale()))
        color = "#57534e" if note is None else note.color
        hover = "" if note is None else "QPushButton:hover { background: #38332f; }"
        button.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-bottom: {stripe}px solid {color};
                border-radius: 4px;
                padding: 3px;
            }}
            {hover}
        """)

    def activate(self, window) -> None:
        window.open_color_picker_for_active()
