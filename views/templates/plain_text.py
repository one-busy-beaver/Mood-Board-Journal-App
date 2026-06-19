from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class PlainTextTemplate(QTextEdit):
    def __init__(self, content: dict, compact: bool = True, parent=None):
        super().__init__(parent)
        self.setPlainText(content.get("body", ""))
        self.setAcceptRichText(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        if compact:
            self.setFont(QFont("Georgia", 9))
            self.setStyleSheet("""
                QTextEdit {
                    background: transparent;
                    border: none;
                    color: #1c1917;
                    selection-background-color: #fde68a;
                    padding: 2px;
                }
                QScrollBar:vertical {
                    width: 4px;
                    background: transparent;
                }
                QScrollBar::handle:vertical {
                    background: #d6d3d1;
                    border-radius: 2px;
                }
            """)
        else:
            self.setFont(QFont("Georgia", 12))
            self.setStyleSheet("""
                QTextEdit {
                    background: transparent;
                    border: none;
                    color: #1c1917;
                    selection-background-color: #fde68a;
                    padding: 4px;
                    line-height: 1.6;
                }
            """)

    def dump(self) -> dict:
        return {"body": self.toPlainText()}
