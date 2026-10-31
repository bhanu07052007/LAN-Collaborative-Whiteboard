"""
Client Application Entry Point for LAN Collaborative Whiteboard.
Orchestrates the lifecycle between ConnectionWindow and MainWindow.
"""

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from client.connection_window import ConnectionWindow
from client.local_state import LocalState
from client.main_window import MainWindow
from client.network_client import NetworkClient


class CollaborativeWhiteboardApp:
    def __init__(self) -> None:
        self.state = LocalState()
        self.network = NetworkClient()

        self.conn_win: Optional[ConnectionWindow] = None
        self.main_win: Optional[MainWindow] = None

        self._pending_action: Optional[str] = None
        self._pending_room_id: Optional[str] = None
        self._pending_room_name: Optional[str] = None
        self._pending_username: Optional[str] = None
        self._pending_password: Optional[str] = None

        self._wire_network_signals()

    def _wire_network_signals(self) -> None:
        self.network.connected_signal.connect(self._on_socket_connected)
        self.network.connection_failed_signal.connect(self._on_connection_failed)
        self.network.room_created_signal.connect(self._on_room_created)
        self.network.join_success_signal.connect(self._on_join_success)
        self.network.join_failure_signal.connect(self._on_join_failure)
        self.network.error_signal.connect(self._on_server_error)

    def start(self) -> None:
        self.show_connection_window()

    def show_connection_window(self) -> None:
        if self.main_win:
            self.main_win.close()
            self.main_win = None

        self.conn_win = ConnectionWindow()
        self.conn_win.create_requested.connect(self._handle_create_request)
        self.conn_win.join_requested.connect(self._handle_join_request)
        self.conn_win.show()

    def _handle_create_request(
        self, host: str, port: int, room_id: str, room_name: str, username: str, password: str
    ) -> None:
        self._pending_action = "create"
        self._pending_room_id = room_id
        self._pending_room_name = room_name
        self._pending_username = username
        self._pending_password = password

        self.state.server_host = host
        self.state.server_port = port
        self.state.username = username

        # Initiate TCP connection
        self.network.connect_to_server(host, port)

    def _handle_join_request(
        self, host: str, port: int, room_id: str, username: str, password: str
    ) -> None:
        self._pending_action = "join"
        self._pending_room_id = room_id
        self._pending_username = username
        self._pending_password = password

        self.state.server_host = host
        self.state.server_port = port
        self.state.username = username

        # Initiate TCP connection
        self.network.connect_to_server(host, port)

    def _on_socket_connected(self) -> None:
        """Triggered when TCP socket handshake completes."""
        if self._pending_action == "create":
            self.network.create_room(
                room_id=self._pending_room_id or "room-1",
                user_id=self.state.user_id,
                username=self._pending_username or "Host",
                room_name=self._pending_room_name,
                password=self._pending_password,
            )
        elif self._pending_action == "join":
            self.network.join_room(
                room_id=self._pending_room_id or "room-1",
                user_id=self.state.user_id,
                username=self._pending_username or "Guest",
                password=self._pending_password,
                user_color=self.state.user_color,
            )

    def _on_connection_failed(self, reason: str) -> None:
        if self.conn_win:
            self.conn_win.show_error(f"Connection failed: {reason}")

    def _on_room_created(self, data: dict) -> None:
        self._open_main_window(data)

    def _on_join_success(self, data: dict) -> None:
        self._open_main_window(data)

    def _on_join_failure(self, reason: str) -> None:
        self.network.disconnect_from_server("Join failed")
        if self.conn_win:
            self.conn_win.show_error(f"Cannot join room: {reason}")

    def _on_server_error(self, message: str) -> None:
        if self.conn_win and self.conn_win.isVisible():
            self.network.disconnect_from_server("Server error")
            self.conn_win.show_error(message)

    def _open_main_window(self, data: dict) -> None:
        room_id = data.get("room_id", self._pending_room_id or "")
        room_name = data.get("room_name", room_id)
        username = data.get("username", self._pending_username or "")
        participants = data.get("participants", [])
        snapshot = data.get("snapshot", {})

        if self.conn_win:
            self.conn_win.hide()

        self.main_win = MainWindow(self.state, self.network)
        self.main_win.update_session_info(room_id, room_name, username, participants, snapshot)

        # Preload chat history if present
        chat_hist = data.get("chat_history", [])
        if chat_hist:
            self.main_win.chat_panel.load_history(chat_hist)

        self.main_win.leave_session_signal.connect(self.show_connection_window)
        self.main_win.show()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("LAN Collaborative Whiteboard")

    whiteboard_app = CollaborativeWhiteboardApp()
    whiteboard_app.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
