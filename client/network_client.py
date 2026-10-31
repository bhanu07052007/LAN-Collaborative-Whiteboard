"""
Network Client for Collaborative Whiteboard.
Runs the socket connection in a separate thread and uses Qt Signals
to communicate asynchronously with the PySide6 GUI thread without freezing the UI.
"""

import logging
import socket
import threading
import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal

from common.constants import (
    DEFAULT_CLIENT_HOST,
    DEFAULT_PORT,
    PING_INTERVAL,
    SOCKET_TIMEOUT,
)
from common.message_types import MessageType
from common.protocol import (
    InvalidMessageError,
    MessageFramingError,
    ProtocolError,
    build_message,
    receive_message,
    send_message,
)

logger = logging.getLogger("NetworkClient")


class NetworkClient(QObject):
    # Qt Signals for GUI integration
    connected_signal = Signal()
    connection_failed_signal = Signal(str)
    disconnected_signal = Signal(str)

    room_created_signal = Signal(dict)
    join_success_signal = Signal(dict)
    join_failure_signal = Signal(str)

    participant_joined_signal = Signal(dict)
    participant_left_signal = Signal(dict)

    state_update_signal = Signal(dict)
    canvas_snapshot_signal = Signal(dict)
    clear_canvas_signal = Signal(dict)

    # Feature 4 & 5 & 6 & 7 Signals
    op_ack_signal = Signal(dict)
    laser_stroke_signal = Signal(dict)
    laser_pointer_signal = Signal(dict)
    file_start_signal = Signal(dict)
    file_chunk_signal = Signal(dict)
    file_complete_signal = Signal(dict)
    meeting_ended_signal = Signal(dict)

    chat_message_signal = Signal(dict)
    error_signal = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._sock: Optional[socket.socket] = None
        self._is_connected = False
        self._send_lock = threading.Lock()

        self._rx_thread: Optional[threading.Thread] = None
        self._ping_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect_to_server(self, host: str, port: int) -> bool:
        """
        Initiates a TCP connection to the specified server host and port.
        Spawns the background receiver thread upon successful connection.
        """
        self.disconnect_from_server()
        self._stop_event.clear()

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)  # Connection timeout
            s.connect((host, port))
            s.settimeout(2.0)  # Read timeout for periodic check of stop_event
            self._sock = s
            self._is_connected = True
        except Exception as e:
            logger.warning("Failed to connect to %s:%s: %s", host, port, e)
            self.connection_failed_signal.emit(f"Could not connect to {host}:{port}: {e}")
            return False

        # Start RX thread
        self._rx_thread = threading.Thread(
            target=self._receive_loop,
            name="Client-RXThread",
            daemon=True,
        )
        self._rx_thread.start()

        # Start Heartbeat thread
        self._ping_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="Client-HeartbeatThread",
            daemon=True,
        )
        self._ping_thread.start()

        logger.info("Successfully connected to server at %s:%d", host, port)
        self.connected_signal.emit()
        return True

    def disconnect_from_server(self, reason: str = "User disconnected") -> None:
        """Closes the socket and terminates background networking threads."""
        if not self._is_connected and not self._sock:
            return

        self._stop_event.set()
        self._is_connected = False

        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
            self._rx_thread = None

        if self._ping_thread and self._ping_thread.is_alive():
            self._ping_thread.join(timeout=1.0)
            self._ping_thread = None

        logger.info("Disconnected from server: %s", reason)
        self.disconnected_signal.emit(reason)

    def send(self, msg_dict: Dict[str, Any]) -> bool:
        """Thread-safe transmission of a protocol message."""
        if not self._is_connected or not self._sock:
            logger.warning("Attempted to send message while disconnected")
            return False

        with self._send_lock:
            try:
                send_message(self._sock, msg_dict)
                return True
            except Exception as e:
                logger.error("Failed to send message: %s", e)
                self.disconnect_from_server(reason=f"Send error: {e}")
                return False

    def _receive_loop(self) -> None:
        """Background thread reading messages from TCP socket."""
        while not self._stop_event.is_set() and self._is_connected:
            if not self._sock:
                break

            try:
                msg = receive_message(self._sock)
            except socket.timeout:
                continue
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError) as e:
                if not self._stop_event.is_set():
                    logger.warning("Connection lost: %s", e)
                    self.disconnect_from_server(reason=f"Connection lost: {e}")
                break
            except (MessageFramingError, InvalidMessageError) as e:
                logger.warning("Protocol framing error: %s", e)
                continue
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.warning("Unexpected network receive error: %s", e)
                    self.disconnect_from_server(reason=f"Network error: {e}")
                break

            if msg is None:
                if not self._stop_event.is_set():
                    logger.info("Server closed connection")
                    self.disconnect_from_server(reason="Server closed connection")
                break

            self._dispatch_message(msg)

    def _heartbeat_loop(self) -> None:
        """Sends periodic PING to server to verify connection health."""
        while not self._stop_event.is_set() and self._is_connected:
            self._stop_event.wait(PING_INTERVAL)
            if self._stop_event.is_set() or not self._is_connected:
                break
            self.send(build_message(MessageType.PING))

    def _dispatch_message(self, msg: Dict[str, Any]) -> None:
        """Dispatches an incoming server message to corresponding Qt signals."""
        msg_type = msg.get("type")
        if not msg_type:
            return

        if msg_type == MessageType.ROOM_CREATED.value:
            self.room_created_signal.emit(msg)

        elif msg_type == MessageType.JOIN_SUCCESS.value:
            self.join_success_signal.emit(msg)

        elif msg_type == MessageType.JOIN_FAILURE.value:
            reason = msg.get("reason", "Failed to join room")
            self.join_failure_signal.emit(reason)

        elif msg_type == MessageType.PARTICIPANT_JOINED.value:
            self.participant_joined_signal.emit(msg)

        elif msg_type == MessageType.PARTICIPANT_LEFT.value:
            self.participant_left_signal.emit(msg)

        elif msg_type == MessageType.STATE_UPDATE.value:
            self.state_update_signal.emit(msg)

        elif msg_type == MessageType.CANVAS_SNAPSHOT.value:
            self.canvas_snapshot_signal.emit(msg)

        elif msg_type == MessageType.CLEAR_CANVAS.value:
            self.clear_canvas_signal.emit(msg)

        elif msg_type == MessageType.OP_ACK.value:
            self.op_ack_signal.emit(msg)

        elif msg_type == MessageType.LASER_STROKE.value:
            self.laser_stroke_signal.emit(msg)

        elif msg_type == MessageType.LASER_POINTER.value:
            self.laser_pointer_signal.emit(msg)

        elif msg_type == MessageType.FILE_START.value:
            self.file_start_signal.emit(msg)

        elif msg_type == MessageType.FILE_CHUNK.value:
            self.file_chunk_signal.emit(msg)

        elif msg_type == MessageType.FILE_COMPLETE.value:
            self.file_complete_signal.emit(msg)

        elif msg_type == MessageType.MEETING_ENDED.value:
            self.meeting_ended_signal.emit(msg)

        elif msg_type == MessageType.CHAT.value:
            self.chat_message_signal.emit(msg)

        elif msg_type == MessageType.ERROR.value:
            self.error_signal.emit(msg.get("message", "Server error"))

        elif msg_type == MessageType.PONG.value:
            # Heartbeat confirmed
            pass

    # High-level Client Actions
    def create_room(
        self,
        room_id: str,
        user_id: str,
        username: str,
        room_name: Optional[str] = None,
        password: Optional[str] = None,
    ) -> bool:
        msg = build_message(
            MessageType.CREATE_ROOM,
            room_id=room_id,
            room_name=room_name or room_id,
            user_id=user_id,
            username=username,
            password=password,
        )
        return self.send(msg)

    def join_room(
        self,
        room_id: str,
        user_id: str,
        username: str,
        password: Optional[str] = None,
        user_color: Optional[str] = None,
    ) -> bool:
        msg = build_message(
            MessageType.JOIN_ROOM,
            room_id=room_id,
            user_id=user_id,
            username=username,
            password=password,
            user_color=user_color,
        )
        return self.send(msg)

    def leave_room(self, room_id: str, user_id: str) -> bool:
        msg = build_message(
            MessageType.LEAVE_ROOM,
            room_id=room_id,
            user_id=user_id,
        )
        return self.send(msg)

    def send_draw_operation(
        self,
        room_id: str,
        user_id: str,
        op_type: str,
        data: Dict[str, Any],
        op_id: Optional[str] = None,
    ) -> bool:
        if op_type == "eraser":
            msg_type = MessageType.ERASE
        elif op_type in ("line", "rect", "circle"):
            msg_type = MessageType.SHAPE
        else:
            msg_type = MessageType.DRAW

        msg = build_message(
            msg_type,
            room_id=room_id,
            user_id=user_id,
            op_id=op_id,
            op_type=op_type,
            data=data,
        )
        return self.send(msg)

    def send_modify_object(
        self,
        room_id: str,
        user_id: str,
        op_id: str,
        new_data: Dict[str, Any],
    ) -> bool:
        msg = build_message(
            MessageType.MODIFY_OBJECT,
            room_id=room_id,
            user_id=user_id,
            op_id=op_id,
            data=new_data,
        )
        return self.send(msg)

    def send_delete_object(self, room_id: str, user_id: str, op_id: str) -> bool:
        msg = build_message(
            MessageType.DELETE_OBJECT,
            room_id=room_id,
            user_id=user_id,
            op_id=op_id,
        )
        return self.send(msg)

    def send_restore_state(self, room_id: str, user_id: str, target_seq: int) -> bool:
        msg = build_message(
            MessageType.RESTORE_STATE,
            room_id=room_id,
            user_id=user_id,
            target_seq=target_seq,
        )
        return self.send(msg)

    def send_laser_stroke(self, room_id: str, user_id: str, points: list, color: str = "#EF4444") -> bool:
        msg = build_message(
            MessageType.LASER_STROKE,
            room_id=room_id,
            user_id=user_id,
            points=points,
            color=color,
        )
        return self.send(msg)

    def send_laser_pointer(self, room_id: str, user_id: str, x: float, y: float, active: bool = True) -> bool:
        msg = build_message(
            MessageType.LASER_POINTER,
            room_id=room_id,
            user_id=user_id,
            x=x,
            y=y,
            active=active,
        )
        return self.send(msg)

    def send_file_start(self, room_id: str, user_id: str, file_id: str, filename: str, file_size: int) -> bool:
        msg = build_message(
            MessageType.FILE_START,
            room_id=room_id,
            user_id=user_id,
            file_id=file_id,
            filename=filename,
            file_size=file_size,
        )
        return self.send(msg)

    def send_file_chunk(
        self,
        room_id: str,
        user_id: str,
        file_id: str,
        chunk_index: int,
        total_chunks: int,
        data_base64: str,
    ) -> bool:
        msg = build_message(
            MessageType.FILE_CHUNK,
            room_id=room_id,
            user_id=user_id,
            file_id=file_id,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            data=data_base64,
        )
        return self.send(msg)

    def send_file_complete(self, room_id: str, user_id: str, file_id: str) -> bool:
        msg = build_message(
            MessageType.FILE_COMPLETE,
            room_id=room_id,
            user_id=user_id,
            file_id=file_id,
        )
        return self.send(msg)

    def send_end_meeting(self, room_id: str, user_id: str) -> bool:
        msg = build_message(
            MessageType.END_MEETING,
            room_id=room_id,
            user_id=user_id,
        )
        return self.send(msg)

    def send_undo(self, room_id: str, user_id: str) -> bool:
        return self.send(build_message(MessageType.UNDO, room_id=room_id, user_id=user_id))

    def send_redo(self, room_id: str, user_id: str) -> bool:
        return self.send(build_message(MessageType.REDO, room_id=room_id, user_id=user_id))

    def send_clear_canvas(self, room_id: str, user_id: str) -> bool:
        return self.send(build_message(MessageType.CLEAR_CANVAS, room_id=room_id, user_id=user_id))

    def send_chat(self, room_id: str, user_id: str, text: str) -> bool:
        return self.send(build_message(MessageType.CHAT, room_id=room_id, user_id=user_id, text=text))
