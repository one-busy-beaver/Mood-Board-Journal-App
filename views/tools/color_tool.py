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
        if note is None:
            # Disabled: muted bucket, dashed neutral stripe
            button.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    border-bottom: 4px solid #57534e;
                    border-radius: 4px;
                    padding: 3px;
                }
            """)
        else:
            button.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    border-bottom: 4px solid {note.color};
                    border-radius: 4px;
                    padding: 3px;
                }}
                QPushButton:hover {{ background: #38332f; }}
            """)

    def activate(self, window) -> None:
        window.open_color_picker_for_active()
