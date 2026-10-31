"""
Participant Panel Widget for Collaborative Whiteboard.
Closely matches the modern dark theme of the reference design (#111D30 / #263E62).
Displays connected room participants with circular avatars, presence badges,
host identification crowns (for the room creator/host), and an '+ Add' room invite button.
"""

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import client.ui_icons as ui_icons


class ParticipantItem(QFrame):
    """Row representing a single connected participant."""

    def __init__(
        self,
        user_id: str,
        username: str,
        color: str,
        is_self: bool = False,
        is_host: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.user_id = user_id
        self.is_self = is_self
        self.is_host = is_host

        self.setStyleSheet("""
            QFrame {
                background-color: #F2F7FF;
                border: 1px solid #AFCDF3;
                border-radius: 8px;
            }
            QFrame:hover {
                background-color: #C8DFFF;
                border-color: #3478F6;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Avatar circle with user's initial
        initial = (username[:1] if username else "U").upper()
        avatar = QLabel(initial, self)
        avatar.setFixedSize(26, 26)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar_bg = color or "#3478F6"
        avatar.setStyleSheet(f"""
            background-color: {avatar_bg};
            color: #FFFFFF;
            font-size: 13px;
            font-weight: bold;
            border-radius: 13px;
            border: 1.5px solid rgba(255, 255, 255, 0.3);
        """)
        layout.addWidget(avatar)

        # Name label with host identification
        if is_self and is_host:
            display_name = f"{username} (You) 👑"
        elif is_self:
            display_name = f"{username} (You)"
        elif is_host:
            display_name = f"{username} (Host) 👑"
        else:
            display_name = username

        name_lbl = QLabel(display_name, self)
        name_lbl.setStyleSheet(f"""
            font-size: 13px;
            color: #172B4D;
            font-weight: {'bold' if (is_self or is_host) else '500'};
            background: transparent;
            border: none;
        """)
        layout.addWidget(name_lbl, 1)

        # Online green indicator dot
        online_dot = QFrame(self)
        online_dot.setFixedSize(8, 8)
        online_dot.setStyleSheet("""
            background-color: #16A878;
            border-radius: 4px;
            border: none;
        """)
        online_dot.setToolTip("Active on LAN")
        layout.addWidget(online_dot)


class ParticipantPanel(QWidget):
    invite_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_user_id: Optional[str] = None
        self._items: Dict[str, ParticipantItem] = {}

        self.setStyleSheet("""
            ParticipantPanel {
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
        icon_lbl.setPixmap(ui_icons.get_tool_icon("participants", color="#172B4D", size=18).pixmap(18, 18))
        header_layout.addWidget(icon_lbl)

        header_lbl = QLabel("Participants", self)
        header_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #172B4D;")
        header_layout.addWidget(header_lbl)

        self.count_badge = QLabel("(0)", self)
        self.count_badge.setStyleSheet("font-size: 13px; font-weight: bold; color: #3478F6;")
        header_layout.addWidget(self.count_badge)

        header_layout.addStretch()

        # "+ Add" Invite Button
        self.add_btn = QPushButton("+ Add", self)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #F2F7FF;
                border: 1px solid #AFCDF3;
                border-radius: 6px;
                color: #172B4D;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #C8DFFF;
                border-color: #3478F6;
            }
        """)
        self.add_btn.setToolTip("Invite participants on your Local Area Network")
        self.add_btn.clicked.connect(self._on_add_clicked)
        header_layout.addWidget(self.add_btn)

        layout.addLayout(header_layout)

        # Scrollable container for participant cards
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(6)
        self.container_layout.addStretch()

        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area, 1)

    def set_current_user_id(self, user_id: str) -> None:
        self.current_user_id = user_id

    def update_participants(self, participants_list: List[Dict[str, Any]]) -> None:
        """Refreshes the full list of participants."""
        self.clear()
        for p in participants_list:
            self.add_participant(p)

    def add_participant(self, p: Dict[str, Any]) -> None:
        user_id = p.get("user_id", "")
        if user_id in self._items:
            return

        username = p.get("username", "Unknown")
        color = p.get("color", "#397BFF")
        is_self = (user_id == self.current_user_id)
        is_host = bool(p.get("is_host", False))

        item = ParticipantItem(user_id, username, color, is_self=is_self, is_host=is_host)
        self._items[user_id] = item

        # Insert before bottom stretch
        self.container_layout.insertWidget(self.container_layout.count() - 1, item)
        self._update_count()

    def remove_participant(self, user_id: str) -> None:
        item = self._items.pop(user_id, None)
        if item:
            self.container_layout.removeWidget(item)
            item.deleteLater()
            self._update_count()

    def clear(self) -> None:
        for item in self._items.values():
            self.container_layout.removeWidget(item)
            item.deleteLater()
        self._items.clear()
        self._update_count()

    def _update_count(self) -> None:
        count = len(self._items)
        self.count_badge.setText(f"({count})")

    def _on_add_clicked(self) -> None:
        self.invite_requested.emit()
