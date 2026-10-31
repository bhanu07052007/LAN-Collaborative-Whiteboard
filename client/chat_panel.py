"""
Chat Panel Widget for Collaborative Whiteboard.
Closely matches the modern dark theme of the reference design (#111D30).
Displays chronological group chat messages with distinctive participant colors,
timestamps, clear chat action, chat history loading with deduplication,
and a modern composer with paper airplane send button.
"""

import time
from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import client.ui_icons as ui_icons

# Accessible vibrant colors for alternating participant usernames on light backgrounds
NAME_COLORS = [
    "#2563EB",  # Royal Blue
    "#059669",  # Emerald Green
    "#7C3AED",  # Vivid Purple
    "#D97706",  # Amber/Bronze
    "#DC2626",  # Crimson Red
    "#DB2777",  # Pink
]


class ChatPanel(QWidget):
    send_message_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_username: str = ""
        self._user_colors: Dict[str, str] = {}
        self._next_color_idx = 0
        self._loaded_message_ids: Set[str] = set()

        self.setStyleSheet("""
            ChatPanel {
                background-color: #DCEBFF;
                border: 1.5px solid #AFCDF3;
                border-radius: 12px;
            }
        """)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header Row
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(ui_icons.get_tool_icon("chat", color="#172B4D", size=18).pixmap(18, 18))
        header_layout.addWidget(icon_lbl)

        header_lbl = QLabel("Group Chat", self)
        header_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #172B4D;")
        header_layout.addWidget(header_lbl)

        header_layout.addStretch()

        # Clear Chat button
        self.clear_btn = QPushButton("🗑 Clear Chat", self)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #F2F7FF;
                border: 1px solid #AFCDF3;
                border-radius: 6px;
                color: #64748B;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #C8DFFF;
                border-color: #3478F6;
                color: #172B4D;
            }
        """)
        self.clear_btn.setToolTip("Clear chat message history")
        self.clear_btn.clicked.connect(self.clear_chat)
        header_layout.addWidget(self.clear_btn)

        layout.addLayout(header_layout)

        # Messages Browser
        self.chat_display = QTextBrowser(self)
        self.chat_display.setOpenExternalLinks(False)
        self.chat_display.setStyleSheet("""
            QTextBrowser {
                background-color: #F2F7FF;
                border: 1px solid #AFCDF3;
                border-radius: 8px;
                padding: 8px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
                color: #172B4D;
            }
        """)
        layout.addWidget(self.chat_display, 1)

        # Composer Row
        input_layout = QHBoxLayout()
        input_layout.setSpacing(6)

        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.setMaxLength(1000)
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #FFFFFF;
                border: 1.5px solid #B8D0EE;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: #172B4D;
            }
            QLineEdit:focus {
                border-color: #3478F6;
                background-color: #FFFFFF;
            }
            QLineEdit::placeholder {
                color: #8294AD;
            }
        """)
        self.input_field.returnPressed.connect(self._on_send_clicked)
        input_layout.addWidget(self.input_field, 1)

        self.send_btn = QPushButton(self)
        self.send_btn.setIcon(ui_icons.get_tool_icon("send", color="#FFFFFF", size=18))
        self.send_btn.setFixedSize(36, 36)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #3478F6;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
            QPushButton:pressed {
                background-color: #1D4ED8;
            }
        """)
        self.send_btn.setToolTip("Send message (Enter)")
        self.send_btn.clicked.connect(self._on_send_clicked)
        input_layout.addWidget(self.send_btn)

        layout.addLayout(input_layout)

    def set_current_username(self, username: str) -> None:
        self.current_username = username

    def _get_user_color(self, username: str) -> str:
        if username not in self._user_colors:
            self._user_colors[username] = NAME_COLORS[self._next_color_idx % len(NAME_COLORS)]
            self._next_color_idx += 1
        return self._user_colors[username]

    def _on_send_clicked(self) -> None:
        text = self.input_field.text().strip()
        if not text:
            return
        self.send_message_requested.emit(text)
        self.input_field.clear()

    def clear_chat(self) -> None:
        self.chat_display.clear()
        self._loaded_message_ids.clear()

    def load_history(self, history: Optional[List[Dict[str, Any]]]) -> None:
        """
        Loads and displays previously saved chat messages in chronological order.
        Handles empty or None history safely and deduplicates messages by message_id.
        """
        if not history:
            return

        # Sort chronologically by timestamp
        sorted_history = sorted(history, key=lambda m: m.get("timestamp", 0))

        for msg in sorted_history:
            msg_id = msg.get("message_id")
            if msg_id and msg_id in self._loaded_message_ids:
                continue

            username = msg.get("username", "Unknown")
            text = msg.get("text", "")
            timestamp = msg.get("timestamp")
            is_self = bool(self.current_username and username == self.current_username)

            self.add_chat_message(
                username=username,
                text=text,
                timestamp=timestamp,
                is_self=is_self,
                message_id=msg_id,
            )

    def add_chat_message(
        self,
        username: str,
        text: str,
        timestamp: Optional[float] = None,
        is_self: bool = False,
        message_id: Optional[str] = None,
    ) -> None:
        """Appends a new formatted message bubble to the chat browser."""
        if message_id:
            if message_id in self._loaded_message_ids:
                return
            self._loaded_message_ids.add(message_id)

        ts = timestamp or time.time()
        time_str = time.strftime("%H:%M:%S", time.localtime(ts))

        clean_text = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

        name_color = self._get_user_color(username)
        display_name = f"{username} (You)" if is_self else username

        html = f"""
        <div style="margin-bottom: 10px; padding: 4px 0;">
            <div style="font-size: 12px; margin-bottom: 3px;">
                <span style="font-weight: bold; color: {name_color};">{display_name}</span>
                <span style="float: right; color: #64748B; font-size: 11px;">{time_str}</span>
            </div>
            <div style="color: #172B4D; font-size: 13px; line-height: 1.4;">{clean_text}</div>
        </div>
        """
        self.chat_display.append(html)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def add_system_message(self, text: str) -> None:
        time_str = time.strftime("%H:%M:%S", time.localtime())
        clean_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f"""
        <div style="text-align: center; margin: 6px 0; color: #64748B; font-size: 11px;">
            <i>[{time_str}] {clean_text}</i>
        </div>
        """
        self.chat_display.append(html)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())
