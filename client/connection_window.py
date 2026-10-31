"""
Connection Window for Collaborative Whiteboard.
Closely matches the modern dark navy & blue design (#080F1C / #0D1728 / #263E62).
Provides two distinct modes:
1. 'Join Existing Room' (Room ID, Password)
2. 'Create New Room' (Room Name, custom/auto-generated Room ID, Optional Password)
"""

import re
import uuid
from typing import Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from common.constants import (
    DEFAULT_CLIENT_HOST,
    DEFAULT_PORT,
    MAX_PASSWORD_LEN,
    MAX_ROOM_ID_LEN,
    MAX_USERNAME_LEN,
    MIN_ROOM_ID_LEN,
    MIN_USERNAME_LEN,
)
import client.ui_icons as ui_icons


class ConnectionWindow(QWidget):
    # Signals emitted to initiate networking action:
    # create_requested: (host, port, room_id, room_name, username, password)
    create_requested = Signal(str, int, str, str, str, str)
    # join_requested: (host, port, room_id, username, password)
    join_requested = Signal(str, int, str, str, str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("LAN Collaborative Whiteboard - Connect")
        self.setMinimumSize(460, 580)
        self.resize(500, 680)
        self._current_mode = "join"  # 'join' or 'create'

        self._apply_stylesheet()
        self._setup_ui()

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background-color: #EAF3FF;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            #cardFrame {
                background-color: #FFFFFF;
                border: 1.5px solid #AFCDF3;
                border-radius: 16px;
                padding: 20px;
            }
            QLabel {
                color: #172B4D;
                font-size: 13px;
                font-weight: 500;
                background-color: transparent;
            }
            QLabel.sectionHeader {
                color: #172B4D;
                font-size: 14px;
                font-weight: 700;
                background-color: transparent;
            }
            QLineEdit {
                background-color: #FFFFFF;
                border: 2px solid #B8D0EE;
                border-radius: 10px;
                padding: 0 12px;
                font-size: 14px;
                color: #172B4D;
                min-height: 42px;
                selection-background-color: #3478F6;
            }
            QLineEdit:focus {
                border-color: #3478F6;
                background-color: #FFFFFF;
            }
            QLineEdit::placeholder {
                color: #8294AD;
            }
            QPushButton.modeTab {
                background-color: #F2F7FF;
                color: #64748B;
                border: 1.5px solid #AFCDF3;
                border-radius: 8px;
                padding: 8px 14px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton.modeTab:hover {
                background-color: #C8DFFF;
                color: #172B4D;
            }
            QPushButton.modeTab:checked {
                background-color: #3478F6;
                color: #FFFFFF;
                border-color: #3478F6;
            }
            QPushButton#btnAction {
                background-color: #3478F6;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton#btnAction:hover {
                background-color: #2563EB;
            }
            QPushButton#btnAction:pressed {
                background-color: #1D4ED8;
            }
            QPushButton#btnAction:disabled {
                background-color: #E2E8F0;
                color: #94A3B8;
            }
        """)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)

        card = QFrame(self)
        card.setObjectName("cardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)

        # Header with Logo & Brand Title
        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        icon_lbl = QLabel(card)
        icon_lbl.setPixmap(ui_icons.get_app_icon(36).pixmap(36, 36))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_box.addWidget(icon_lbl)

        title_lbl = QLabel("Collaborative Whiteboard", card)
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 800; color: #172B4D;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_box.addWidget(title_lbl)

        sub_lbl = QLabel("LAN-Based Real-Time Visual Collaboration", card)
        sub_lbl.setStyleSheet("font-size: 12px; color: #64748B;")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_box.addWidget(sub_lbl)
        card_layout.addLayout(title_box)

        # Mode Selector Buttons: [ Join Existing Room ] | [ Create New Room ]
        mode_box = QHBoxLayout()
        mode_box.setSpacing(8)

        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)

        self.tab_join = QPushButton("Join Existing Room", card)
        self.tab_join.setProperty("class", "modeTab")
        self.tab_join.setCheckable(True)
        self.tab_join.setChecked(True)
        self.tab_join.clicked.connect(lambda: self._set_mode("join"))
        self.mode_group.addButton(self.tab_join)
        mode_box.addWidget(self.tab_join)

        self.tab_create = QPushButton("Create New Room", card)
        self.tab_create.setProperty("class", "modeTab")
        self.tab_create.setCheckable(True)
        self.tab_create.setChecked(False)
        self.tab_create.clicked.connect(lambda: self._set_mode("create"))
        self.mode_group.addButton(self.tab_create)
        mode_box.addWidget(self.tab_create)

        card_layout.addLayout(mode_box)

        # Form Fields Grid
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setVerticalSpacing(8)

        # Username
        grid.addWidget(QLabel("Your Username:", card), 0, 0, 1, 2)
        self.username_input = QLineEdit(card)
        self.username_input.setPlaceholderText("e.g. Engineer")
        self.username_input.setText("Engineer")
        self.username_input.setMaxLength(MAX_USERNAME_LEN)
        self.username_input.setFixedHeight(42)
        self.username_input.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.username_input, 1, 0, 1, 2)

        # Server IP & Port
        grid.addWidget(QLabel("Server IP Address:", card), 2, 0)
        grid.addWidget(QLabel("Port:", card), 2, 1)

        self.ip_input = QLineEdit(card)
        self.ip_input.setPlaceholderText("e.g. 192.168.1.5 or 127.0.0.1")
        self.ip_input.setText(DEFAULT_CLIENT_HOST)
        self.ip_input.setFixedHeight(42)
        self.ip_input.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.ip_input, 3, 0)

        self.port_input = QLineEdit(card)
        self.port_input.setPlaceholderText("8555")
        self.port_input.setText(str(DEFAULT_PORT))
        self.port_input.setFixedWidth(90)
        self.port_input.setFixedHeight(42)
        self.port_input.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.port_input, 3, 1)

        # Dynamic Field 1: Room Name (Visible in Create mode) / Room ID (in Join mode)
        self.lbl_field1 = QLabel("Room Identifier:", card)
        grid.addWidget(self.lbl_field1, 4, 0, 1, 2)

        self.input_field1 = QLineEdit(card)
        self.input_field1.setPlaceholderText("e.g. room-1")
        self.input_field1.setText("room-1")
        self.input_field1.setMaxLength(MAX_ROOM_ID_LEN)
        self.input_field1.setFixedHeight(42)
        self.input_field1.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.input_field1, 5, 0, 1, 2)

        # Dynamic Field 2: Custom Room ID (Visible in Create mode only)
        self.lbl_field2 = QLabel("Custom Room ID (Optional):", card)
        grid.addWidget(self.lbl_field2, 6, 0, 1, 2)

        self.input_field2 = QLineEdit(card)
        self.input_field2.setPlaceholderText("Leave blank to auto-generate unique ID")
        self.input_field2.setMaxLength(MAX_ROOM_ID_LEN)
        self.input_field2.setFixedHeight(42)
        self.input_field2.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.input_field2, 7, 0, 1, 2)

        # Room Password
        grid.addWidget(QLabel("Room Password (Optional):", card), 8, 0, 1, 2)
        self.password_input = QLineEdit(card)
        self.password_input.setPlaceholderText("Leave blank if public")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMaxLength(MAX_PASSWORD_LEN)
        self.password_input.setFixedHeight(42)
        self.password_input.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.password_input, 9, 0, 1, 2)

        # Show Password Checkbox
        self.show_pwd_cb = QCheckBox("Show password", card)
        self.show_pwd_cb.setStyleSheet("font-size: 11px; color: #64748B;")
        self.show_pwd_cb.toggled.connect(self._toggle_password_visibility)
        grid.addWidget(self.show_pwd_cb, 10, 0, 1, 2)

        card_layout.addLayout(grid)

        # Status / Error Message Label
        self.status_lbl = QLabel("", card)
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet("font-size: 12px; font-weight: bold; min-height: 20px;")
        card_layout.addWidget(self.status_lbl)

        # Primary Action Button
        self.btn_action = QPushButton("Join Room", card)
        self.btn_action.setObjectName("btnAction")
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.clicked.connect(self._on_action_clicked)
        card_layout.addWidget(self.btn_action)

        main_layout.addWidget(card)
        self._set_mode("join")

    def _set_mode(self, mode: str) -> None:
        self._current_mode = mode
        self.status_lbl.setText("")
        if mode == "join":
            self.lbl_field1.setText("Room Identifier:")
            self.input_field1.setPlaceholderText("e.g. room-1")
            if not self.input_field1.text().strip():
                self.input_field1.setText("room-1")
            self.lbl_field2.setVisible(False)
            self.input_field2.setVisible(False)
            self.btn_action.setText("Join Room")
        else:
            self.lbl_field1.setText("Room Name:")
            self.input_field1.setPlaceholderText("e.g. Sprint Planning")
            self.input_field1.setText("Design Collaboration")
            self.lbl_field2.setVisible(True)
            self.input_field2.setVisible(True)
            self.btn_action.setText("Create New Room")

    def _toggle_password_visibility(self, checked: bool) -> None:
        self.password_input.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)

    def _validate_common_inputs(self) -> Optional[Tuple[str, int, str, Optional[str]]]:
        username = self.username_input.text().strip()
        if not (MIN_USERNAME_LEN <= len(username) <= MAX_USERNAME_LEN):
            self.show_error(f"Username must be {MIN_USERNAME_LEN} to {MAX_USERNAME_LEN} characters")
            return None

        ip = self.ip_input.text().strip()
        if not ip:
            self.show_error("Server IP address cannot be empty")
            return None

        port_str = self.port_input.text().strip()
        try:
            port = int(port_str)
            if not (1 <= port <= 65535):
                raise ValueError()
        except ValueError:
            self.show_error("Port must be a valid number between 1 and 65535")
            return None

        pwd = self.password_input.text().strip()
        return ip, port, username, (pwd if pwd else None)

    def _on_action_clicked(self) -> None:
        common = self._validate_common_inputs()
        if not common:
            return
        ip, port, username, password = common

        if self._current_mode == "join":
            room_id = self.input_field1.text().strip()
            if not (MIN_ROOM_ID_LEN <= len(room_id) <= MAX_ROOM_ID_LEN):
                self.show_error(f"Room ID must be {MIN_ROOM_ID_LEN} to {MAX_ROOM_ID_LEN} characters")
                return
            self.set_loading(True, f"Connecting to server and joining '{room_id}'...")
            self.join_requested.emit(ip, port, room_id, username, password or "")

        else:
            room_name = self.input_field1.text().strip()
            if not room_name:
                self.show_error("Please enter a Room Name")
                return

            custom_id = self.input_field2.text().strip()
            if custom_id:
                clean_id = re.sub(r"[^a-zA-Z0-9_-]", "-", custom_id).strip("-").lower()
                if not (MIN_ROOM_ID_LEN <= len(clean_id) <= MAX_ROOM_ID_LEN):
                    self.show_error(f"Custom Room ID must be {MIN_ROOM_ID_LEN} to {MAX_ROOM_ID_LEN} alphanumeric chars")
                    return
                room_id = clean_id
            else:
                # Auto-generate friendly unique slug from room name
                slug = re.sub(r"[^a-zA-Z0-9_-]", "-", room_name).strip("-").lower()
                if len(slug) >= 3:
                    room_id = f"{slug[:18]}-{uuid.uuid4().hex[:4]}"
                else:
                    room_id = f"room-{uuid.uuid4().hex[:6]}"

            self.set_loading(True, f"Connecting to server and creating room '{room_name}'...")
            self.create_requested.emit(ip, port, room_id, room_name, username, password or "")

    def show_error(self, message: str) -> None:
        self.status_lbl.setText(message)
        self.status_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #F87171;")
        self.set_loading(False)

    def show_info(self, message: str) -> None:
        self.status_lbl.setText(message)
        self.status_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #20D6A0;")

    def set_loading(self, loading: bool, message: str = "") -> None:
        self.btn_action.setEnabled(not loading)
        self.tab_join.setEnabled(not loading)
        self.tab_create.setEnabled(not loading)
        if loading and message:
            self.status_lbl.setText(message)
            self.status_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #397BFF;")
