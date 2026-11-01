"""
TCP Socket Server for LAN-Based Collaborative Whiteboard.
Handles multi-client TCP connections, thread-per-client message handling,
operation distribution, access control, and room lifecycle management.
"""

import logging
import socket
import threading
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from common.constants import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    PING_INTERVAL,
    PING_TIMEOUT,
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
    validate_message,
)
from server.chat_manager import ChatManager
from server.connection_manager import ConnectionManager
from server.meeting_report_manager import MeetingReportManager
from server.persistence_manager import PersistenceManager
from server.server_config import ServerConfig
from server.session_manager import SessionManager
from server.whiteboard_manager import WhiteboardManager

logger = logging.getLogger("SocketServer")


class SocketServer:
    def __init__(self, config: Optional[ServerConfig] = None) -> None:
        self.config = config or ServerConfig()
        self.connection_mgr = ConnectionManager()
        self.session_mgr = SessionManager()
        self.whiteboard_mgr = WhiteboardManager()
        self.chat_mgr = ChatManager()
        self.persistence_mgr = PersistenceManager(self.config.sessions_dir)
        self.report_mgr = MeetingReportManager(self.config.meeting_logs_dir)

        self._server_sock: Optional[socket.socket] = None
        self._is_running = False
        self._accept_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._client_threads: Dict[str, threading.Thread] = {}
        self._threads_lock = threading.Lock()

        # Restore previously persisted rooms
        restored = self.persistence_mgr.restore_all_rooms(
            self.session_mgr, self.whiteboard_mgr, self.chat_mgr
        )
        logger.info("Restored %d rooms from persistent storage", restored)

    def start(self) -> None:
        """Starts listening for incoming client TCP connections."""
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self._server_sock.bind((self.config.host, self.config.port))
        except OSError as e:
            logger.error("Failed to bind socket to %s:%s: %s", self.config.host, self.config.port, e)
            raise

        self._server_sock.listen(128)
        self._server_sock.settimeout(1.0)  # Allows check for self._is_running
        self._is_running = True

        # Launch accept thread
        self._accept_thread = threading.Thread(target=self._accept_loop, name="AcceptThread", daemon=True)
        self._accept_thread.start()

        # Launch monitor thread (health checks & periodic persistence)
        self._monitor_thread = threading.Thread(target=self._monitor_loop, name="MonitorThread", daemon=True)
        self._monitor_thread.start()

        lan_ips = self.config.get_local_lan_ips()
        logger.info("Server started on port %d", self.config.port)
        logger.info("Available LAN IP addresses: %s", ", ".join(lan_ips))

    def stop(self) -> None:
        """Gracefully terminates the server and cleans up connections."""
        if not self._is_running:
            return

        logger.info("Initiating server shutdown...")
        self._is_running = False

        # Close server socket to unblock accept loop
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass

        # Disconnect all active clients
        for client in self.connection_mgr.get_room_clients(""):
            self.connection_mgr.unregister_client(client.user_id)

        # Wait for threads
        if self._accept_thread and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=2.0)
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)

        # Save all room states and finalize meeting reports before exiting
        for room_info in self.session_mgr.list_rooms():
            rid = room_info["room_id"]
            room = self.session_mgr.get_room(rid)
            wb = self.whiteboard_mgr.get_room_whiteboard(rid)
            if room:
                self.persistence_mgr.save_room_state(room, self.whiteboard_mgr, self.chat_mgr)
            tracker = self.report_mgr.get_tracker(rid)
            if tracker and tracker.end_time is None:
                tracker.finish_session(reason="Server shutdown")
                tracker.write_report_to_disk(
                    final_op_count=wb.current_seq_num if wb else 0,
                    persistence_path=f"data/sessions/{rid}.json",
                )

        logger.info("Server stopped cleanly.")

    def _accept_loop(self) -> None:
        """Accepts incoming TCP client connections."""
        while self._is_running:
            try:
                if not self._server_sock:
                    break
                client_sock, address = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            client_sock.settimeout(self.config.socket_timeout)
            # Create a temporary ID until the client identifies itself in handshake
            temp_id = f"preauth-{uuid.uuid4().hex[:8]}"
            logger.info("New connection accepted from %s:%s (temp ID %s)", address[0], address[1], temp_id)

            t = threading.Thread(
                target=self._handle_client,
                args=(client_sock, address, temp_id),
                name=f"Client-{address[0]}:{address[1]}",
                daemon=True,
            )
            with self._threads_lock:
                self._client_threads[temp_id] = t
            t.start()

    def _handle_client(self, sock: socket.socket, address: Tuple[str, int], temp_id: str) -> None:
        """Worker thread handling the TCP stream for a single client."""
        user_id: Optional[str] = None
        current_room_id: Optional[str] = None

        try:
            while self._is_running:
                try:
                    msg = receive_message(sock)
                except socket.timeout:
                    # Timeout triggered, send a ping or continue
                    continue
                except (ConnectionResetError, MessageFramingError, InvalidMessageError) as e:
                    logger.debug("Socket read error from %s: %s", address, e)
                    break
                except Exception as e:
                    logger.warning("Unexpected error reading from %s: %s", address, e)
                    break

                if msg is None:
                    # Client closed connection cleanly
                    logger.info("Client %s:%s disconnected (EOF)", address[0], address[1])
                    break

                # Validate message format
                is_valid, reason = validate_message(msg)
                if not is_valid:
                    send_message(sock, build_message(MessageType.ERROR, message=f"Invalid message format: {reason}"))
                    continue

                msg_type = msg.get("type")
                # Handle ping/pong immediately
                if msg_type == MessageType.PING.value:
                    send_message(sock, build_message(MessageType.PONG))
                    if user_id:
                        self.connection_mgr.update_activity(user_id)
                    continue

                if msg_type == MessageType.PONG.value:
                    if user_id:
                        self.connection_mgr.update_activity(user_id)
                    continue

                # Session & authentication messages
                if msg_type == MessageType.CREATE_ROOM.value:
                    user_id, current_room_id = self._handle_create_room(sock, address, msg)

                elif msg_type == MessageType.JOIN_ROOM.value:
                    user_id, current_room_id = self._handle_join_room(sock, address, msg)

                elif msg_type == MessageType.LEAVE_ROOM.value:
                    if user_id and current_room_id:
                        self._handle_leave_room(user_id, current_room_id)
                        current_room_id = None

                # Whiteboard & drawing operations
                elif msg_type in (
                    MessageType.DRAW.value,
                    MessageType.ERASE.value,
                    MessageType.SHAPE.value,
                    "pen",
                    "eraser",
                    "line",
                    "rect",
                    "circle",
                    "text",
                    "sticky",
                ):
                    if "op_type" not in msg or not msg["op_type"]:
                        msg["op_type"] = msg_type if msg_type in ("pen", "eraser", "line", "rect", "circle", "text", "sticky") else "pen"
                    if user_id and current_room_id:
                        self._handle_draw_op(user_id, current_room_id, msg)
                    else:
                        send_message(sock, build_message(MessageType.ERROR, message="Not joined to any room"))

                elif msg_type == MessageType.MODIFY_OBJECT.value:
                    if user_id and current_room_id:
                        self._handle_modify_object(user_id, current_room_id, msg)

                elif msg_type == MessageType.DELETE_OBJECT.value:
                    if user_id and current_room_id:
                        self._handle_delete_object(user_id, current_room_id, msg)

                elif msg_type == MessageType.RESTORE_STATE.value:
                    if user_id and current_room_id:
                        self._handle_restore_state(user_id, current_room_id, msg)

                elif msg_type == MessageType.UNDO.value:
                    if user_id and current_room_id:
                        self._handle_undo(user_id, current_room_id)

                elif msg_type == MessageType.REDO.value:
                    if user_id and current_room_id:
                        self._handle_redo(user_id, current_room_id)

                elif msg_type == MessageType.CLEAR_CANVAS.value:
                    if user_id and current_room_id:
                        self._handle_clear_canvas(user_id, current_room_id)

                # Laser Presentation Tools
                elif msg_type == MessageType.LASER_STROKE.value:
                    if user_id and current_room_id:
                        self._handle_laser_stroke(user_id, current_room_id, msg)

                elif msg_type == MessageType.LASER_POINTER.value:
                    if user_id and current_room_id:
                        self._handle_laser_pointer(user_id, current_room_id, msg)

                # Chunked File Transfer
                elif msg_type == MessageType.FILE_START.value:
                    if user_id and current_room_id:
                        self._handle_file_start(user_id, current_room_id, msg)

                elif msg_type == MessageType.FILE_CHUNK.value:
                    if user_id and current_room_id:
                        self._handle_file_chunk(user_id, current_room_id, msg)

                elif msg_type == MessageType.FILE_COMPLETE.value:
                    if user_id and current_room_id:
                        self._handle_file_complete(user_id, current_room_id, msg)

                # Meeting Lifecycle
                elif msg_type == MessageType.END_MEETING.value:
                    if user_id and current_room_id:
                        self._handle_end_meeting(user_id, current_room_id, msg)

                # Group chat
                elif msg_type == MessageType.CHAT.value:
                    if user_id and current_room_id:
                        self._handle_chat(user_id, current_room_id, msg)

                if user_id:
                    self.connection_mgr.update_activity(user_id)

        finally:
            # Cleanup on disconnect
            if user_id:
                if current_room_id:
                    self._handle_leave_room(user_id, current_room_id)
                self.connection_mgr.unregister_client(user_id)
            else:
                try:
                    sock.close()
                except OSError:
                    pass

            with self._threads_lock:
                self._client_threads.pop(temp_id, None)
                if user_id:
                    self._client_threads.pop(user_id, None)

    def _handle_create_room(
        self, sock: socket.socket, address: Tuple[str, int], msg: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Handles room creation request and registers the creator."""
        room_id = msg.get("room_id", "").strip()
        room_name = msg.get("room_name", room_id).strip()
        username = msg.get("username", "Host").strip()
        user_id = msg.get("user_id") or f"user-{uuid.uuid4().hex[:8]}"
        password = msg.get("password")

        success, reason, room = self.session_mgr.create_room(
            room_id=room_id,
            creator_id=user_id,
            room_name=room_name,
            password=password,
        )

        if not success or not room:
            send_message(sock, build_message(MessageType.ERROR, message=f"Failed to create room: {reason}"))
            return None, None

        # Join creator to room
        _, _, participant, _ = self.session_mgr.join_room(
            room_id=room_id,
            user_id=user_id,
            username=username,
            password=password,
        )

        # Register in connection manager
        self.connection_mgr.register_client(
            user_id=user_id,
            username=participant.username if participant else username,
            sock=sock,
            address=address,
            room_id=room_id,
        )

        wb = self.whiteboard_mgr.get_or_create_room_whiteboard(room_id)
        chat = self.chat_mgr.get_or_create_room_chat(room_id)

        # Track session
        self.report_mgr.get_or_create_tracker(
            room_id=room.room_id,
            room_name=room.room_name,
            host_id=user_id,
            host_name=participant.username if participant else username,
        )

        resp = build_message(
            MessageType.ROOM_CREATED,
            room_id=room.room_id,
            room_name=room.room_name,
            has_password=room.has_password,
            user_id=user_id,
            username=participant.username if participant else username,
            color=participant.color if participant else "#3B82F6",
            participants=room.list_participants(),
            snapshot=wb.get_snapshot(),
            seq_num=wb.current_seq_num,
            is_host=True,
        )
        self.connection_mgr.send_to_client(user_id, resp)

        # Persist room
        self.persistence_mgr.save_room_state(room, self.whiteboard_mgr, self.chat_mgr)
        return user_id, room_id

    def _handle_join_room(
        self, sock: socket.socket, address: Tuple[str, int], msg: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Handles room join request and delivers initial canvas snapshot."""
        room_id = msg.get("room_id", "").strip()
        username = msg.get("username", "Guest").strip()
        user_id = msg.get("user_id") or f"user-{uuid.uuid4().hex[:8]}"
        password = msg.get("password")
        user_color = msg.get("user_color")

        success, reason, participant, room = self.session_mgr.join_room(
            room_id=room_id,
            user_id=user_id,
            username=username,
            password=password,
            user_color=user_color,
        )

        if not success or not participant or not room:
            send_message(
                sock,
                build_message(
                    MessageType.JOIN_FAILURE,
                    room_id=room_id,
                    reason=reason,
                ),
            )
            return None, None

        # Register connection
        self.connection_mgr.register_client(
            user_id=user_id,
            username=participant.username,
            sock=sock,
            address=address,
            room_id=room_id,
        )

        wb = self.whiteboard_mgr.get_or_create_room_whiteboard(room_id)
        chat = self.chat_mgr.get_or_create_room_chat(room_id)

        # Track session join
        tracker = self.report_mgr.get_or_create_tracker(
            room_id=room.room_id,
            room_name=room.room_name,
            host_id=room.creator_id,
            host_name=username if user_id == room.creator_id else "Host",
        )
        tracker.record_join(user_id=user_id, username=participant.username, is_host=(user_id == room.creator_id))

        # Send JOIN_SUCCESS with authoritative snapshot and recent chat
        resp = build_message(
            MessageType.JOIN_SUCCESS,
            room_id=room.room_id,
            room_name=room.room_name,
            user_id=user_id,
            username=participant.username,
            color=participant.color,
            participants=room.list_participants(),
            snapshot=wb.get_snapshot(),
            seq_num=wb.current_seq_num,
            chat_history=chat.get_history(limit=50),
            is_host=(user_id == room.creator_id),
        )
        self.connection_mgr.send_to_client(user_id, resp)

        # Notify other participants that this user joined
        notify = build_message(
            MessageType.PARTICIPANT_JOINED,
            room_id=room_id,
            user_id=user_id,
            username=participant.username,
            color=participant.color,
        )
        self.connection_mgr.broadcast_to_room(room_id, notify, exclude_user_id=user_id)

        # Persist room state
        self.persistence_mgr.save_room_state(room, self.whiteboard_mgr, self.chat_mgr)
        return user_id, room_id

    def _handle_leave_room(self, user_id: str, room_id: str) -> None:
        """Removes participant from room and notifies others."""
        success, participant = self.session_mgr.leave_room(room_id, user_id)
        self.connection_mgr.set_client_room(user_id, None)

        # Record leave in meeting audit tracker
        tracker = self.report_mgr.get_tracker(room_id)
        if tracker:
            tracker.record_leave(user_id, early_exit=True)

        if participant:
            notify = build_message(
                MessageType.PARTICIPANT_LEFT,
                room_id=room_id,
                user_id=user_id,
                username=participant.username,
            )
            self.connection_mgr.broadcast_to_room(room_id, notify)

            room = self.session_mgr.get_room(room_id)
            if room:
                self.persistence_mgr.save_room_state(room, self.whiteboard_mgr, self.chat_mgr)

    def _handle_draw_op(self, user_id: str, room_id: str, msg: Dict[str, Any]) -> None:
        """Validates and sequences a drawing operation, broadcasting it to all participants."""
        client = self.connection_mgr.get_client(user_id)
        username = client.username if client else "User"

        wb = self.whiteboard_mgr.get_or_create_room_whiteboard(room_id)
        success, reason, op = wb.add_operation(msg, user_id, username)

        if not success or not op:
            self.connection_mgr.send_to_client(
                user_id,
                build_message(MessageType.ERROR, message=f"Rejected drawing operation: {reason}"),
            )
            return

        # Feature 5: Send Delivery Acknowledgement (OP_ACK) to originator
        ack = build_message(
            MessageType.OP_ACK,
            op_id=op.op_id,
            seq_num=op.seq_num,
            status="accepted",
        )
        self.connection_mgr.send_to_client(user_id, ack)

        # Feature 7: Record drawing in session report
        tracker = self.report_mgr.get_tracker(room_id)
        if tracker:
            tracker.record_drawing(user_id, op.op_type, op.op_id, op.seq_num)

        # Broadcast accepted operation to ALL participants in the room
        update = build_message(
            MessageType.STATE_UPDATE,
            room_id=room_id,
            action="draw",
            seq_num=op.seq_num,
            operation=op.to_dict(),
        )
        self.connection_mgr.broadcast_to_room(room_id, update)

    def _handle_modify_object(self, user_id: str, room_id: str, msg: Dict[str, Any]) -> None:
        """Modifies existing canvas object (move, resize, text, color)."""
        op_id = msg.get("op_id")
        new_data = msg.get("data", {})
        client = self.connection_mgr.get_client(user_id)
        username = client.username if client else "User"

        wb = self.whiteboard_mgr.get_or_create_room_whiteboard(room_id)
        success, reason, op = wb.modify_operation(op_id, new_data, user_id, username)

        if not success or not op:
            self.connection_mgr.send_to_client(
                user_id,
                build_message(MessageType.ERROR, message=f"Modify failed: {reason}"),
            )
            return

        # Delivery ACK
        ack = build_message(MessageType.OP_ACK, op_id=op.op_id, seq_num=op.seq_num, status="accepted")
        self.connection_mgr.send_to_client(user_id, ack)

        update = build_message(
            MessageType.STATE_UPDATE,
            room_id=room_id,
            action="modify",
            seq_num=op.seq_num,
            operation=op.to_dict(),
        )
        self.connection_mgr.broadcast_to_room(room_id, update)

    def _handle_delete_object(self, user_id: str, room_id: str, msg: Dict[str, Any]) -> None:
        """Deletes an object from the shared canvas."""
        op_id = msg.get("op_id")
        wb = self.whiteboard_mgr.get_or_create_room_whiteboard(room_id)
        success, reason, op = wb.delete_operation(op_id, user_id)

        if not success or not op:
            self.connection_mgr.send_to_client(
                user_id,
                build_message(MessageType.ERROR, message=f"Delete failed: {reason}"),
            )
            return

        ack = build_message(MessageType.OP_ACK, op_id=op.op_id, seq_num=op.seq_num, status="accepted")
        self.connection_mgr.send_to_client(user_id, ack)

        update = build_message(
            MessageType.STATE_UPDATE,
            room_id=room_id,
            action="delete",
            seq_num=op.seq_num,
            op_id=op.op_id,
            is_deleted=True,
            operation=op.to_dict(),
        )
        self.connection_mgr.broadcast_to_room(room_id, update)

    def _handle_restore_state(self, user_id: str, room_id: str, msg: Dict[str, Any]) -> None:
        """Restores canvas state to a historical sequence number."""
        target_seq = msg.get("target_seq", 0)
        wb = self.whiteboard_mgr.get_or_create_room_whiteboard(room_id)
        success, reason, active_ops = wb.restore_to_seq(target_seq)

        if not success:
            self.connection_mgr.send_to_client(
                user_id,
                build_message(MessageType.ERROR, message=f"Restore failed: {reason}"),
            )
            return

        update = build_message(
            MessageType.STATE_UPDATE,
            room_id=room_id,
            action="restore",
            seq_num=wb.current_seq_num,
            operations=[op.to_dict() for op in active_ops],
        )
        self.connection_mgr.broadcast_to_room(room_id, update)

    def _handle_laser_stroke(self, user_id: str, room_id: str, msg: Dict[str, Any]) -> None:
        """Relays ephemeral glowing laser stroke to all clients."""
        client = self.connection_mgr.get_client(user_id)
        username = client.username if client else "User"
        msg["sender_id"] = user_id
        msg["sender_name"] = username
        self.connection_mgr.broadcast_to_room(room_id, msg, exclude_user_id=user_id)

    def _handle_laser_pointer(self, user_id: str, room_id: str, msg: Dict[str, Any]) -> None:
        """Relays real-time laser pointer coordinates."""
        client = self.connection_mgr.get_client(user_id)
        username = client.username if client else "User"
        msg["sender_id"] = user_id
        msg["sender_name"] = username
        self.connection_mgr.broadcast_to_room(room_id, msg, exclude_user_id=user_id)

    def _handle_file_start(self, user_id: str, room_id: str, msg: Dict[str, Any]) -> None:
        """Initiates chunked file transfer over TCP."""
        client = self.connection_mgr.get_client(user_id)
        username = client.username if client else "User"
        filename = msg.get("filename", "file")
        file_size = msg.get("file_size", 0)

        from common.constants import MAX_FILE_SIZE
        if file_size > MAX_FILE_SIZE:
            self.connection_mgr.send_to_client(
                user_id,
                build_message(MessageType.ERROR, message=f"File exceeds maximum size {MAX_FILE_SIZE} bytes"),
            )
            return

        msg["sender_id"] = user_id
        msg["sender_name"] = username

        tracker = self.report_mgr.get_tracker(room_id)
        if tracker:
            tracker.record_file_shared(user_id, filename, file_size)

        # Broadcast file transfer initiation to room
        self.connection_mgr.broadcast_to_room(room_id, msg, exclude_user_id=user_id)

        # Post notice in group chat
        size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024 else f"{file_size / (1024 * 1024):.1f} MB"
        chat = self.chat_mgr.get_or_create_room_chat(room_id)
        chat.add_message("system", "System", f"{username} shared file '{filename}' ({size_str})")
        self.connection_mgr.broadcast_to_room(
            room_id,
            build_message(
                MessageType.CHAT,
                room_id=room_id,
                message_id=f"sys-{uuid.uuid4().hex[:8]}",
                user_id="system",
                username="System",
                text=f"{username} shared '{filename}' ({size_str})",
                timestamp=time.time(),
            ),
        )

    def _handle_file_chunk(self, user_id: str, room_id: str, msg: Dict[str, Any]) -> None:
        """Forwards binary file chunk across TCP."""
        self.connection_mgr.broadcast_to_room(room_id, msg, exclude_user_id=user_id)

    def _handle_file_complete(self, user_id: str, room_id: str, msg: Dict[str, Any]) -> None:
        """Signals completed file transfer."""
        self.connection_mgr.broadcast_to_room(room_id, msg, exclude_user_id=user_id)

    def _handle_end_meeting(self, user_id: str, room_id: str, msg: Dict[str, Any]) -> None:
        """Host terminates the meeting and generates session report. Rejects unauthorized attempts."""
        room = self.session_mgr.get_room(room_id)
        if not room or room.creator_id != user_id:
            logger.warning("Unauthorized END_MEETING attempt in room %s by user %s (host is %s)",
                           room_id, user_id, room.creator_id if room else "None")
            self.connection_mgr.send_to_client(
                user_id,
                build_message(MessageType.ERROR, message="Only the meeting host can end the meeting"),
            )
            return

        client = self.connection_mgr.get_client(user_id)
        username = client.username if client else "Host"
        wb = self.whiteboard_mgr.get_or_create_room_whiteboard(room_id)

        # Persist room state
        if room:
            self.persistence_mgr.save_room_state(room, self.whiteboard_mgr, self.chat_mgr)

        # Generate session audit report
        report_path_str = ""
        tracker = self.report_mgr.get_tracker(room_id)
        if tracker:
            tracker.finish_session(reason=f"Meeting ended by host {username}")
            path = tracker.write_report_to_disk(
                final_op_count=wb.current_seq_num,
                persistence_path=f"data/sessions/{room_id}.json",
            )
            report_path_str = str(path)

        ended_msg = build_message(
            MessageType.MEETING_ENDED,
            room_id=room_id,
            host_id=user_id,
            host_name=username,
            report_file=report_path_str,
        )
        self.connection_mgr.broadcast_to_room(room_id, ended_msg)
        logger.info("Meeting for room %s ended by %s. Report saved to %s", room_id, username, report_path_str)

    def _handle_undo(self, user_id: str, room_id: str) -> None:
        """Handles client undo request."""
        wb = self.whiteboard_mgr.get_or_create_room_whiteboard(room_id)
        success, reason, affected_op = wb.undo_last_user_operation(user_id)

        if not success or not affected_op:
            self.connection_mgr.send_to_client(
                user_id,
                build_message(MessageType.ERROR, message=reason),
            )
            return

        update = build_message(
            MessageType.STATE_UPDATE,
            room_id=room_id,
            action="undo",
            seq_num=wb.current_seq_num,
            op_id=affected_op.op_id,
            user_id=user_id,
            is_deleted=affected_op.is_deleted,
            operation=affected_op.to_dict(),
        )
        self.connection_mgr.broadcast_to_room(room_id, update)

    def _handle_redo(self, user_id: str, room_id: str) -> None:
        """Handles client redo request."""
        wb = self.whiteboard_mgr.get_or_create_room_whiteboard(room_id)
        success, reason, affected_op = wb.redo_last_user_operation(user_id)

        if not success or not affected_op:
            self.connection_mgr.send_to_client(
                user_id,
                build_message(MessageType.ERROR, message=reason),
            )
            return

        update = build_message(
            MessageType.STATE_UPDATE,
            room_id=room_id,
            action="redo",
            seq_num=wb.current_seq_num,
            op_id=affected_op.op_id,
            user_id=user_id,
            is_deleted=affected_op.is_deleted,
            operation=affected_op.to_dict(),
        )
        self.connection_mgr.broadcast_to_room(room_id, update)

    def _handle_clear_canvas(self, user_id: str, room_id: str) -> None:
        """Handles canvas reset request."""
        client = self.connection_mgr.get_client(user_id)
        username = client.username if client else "User"

        wb = self.whiteboard_mgr.get_or_create_room_whiteboard(room_id)
        new_seq, cleared_count = wb.clear_canvas(user_id, username)

        tracker = self.report_mgr.get_tracker(room_id)
        if tracker:
            tracker.record_clear(user_id, username, new_seq)

        msg = build_message(
            MessageType.CLEAR_CANVAS,
            room_id=room_id,
            seq_num=new_seq,
            user_id=user_id,
            username=username,
            cleared_count=cleared_count,
        )
        self.connection_mgr.broadcast_to_room(room_id, msg)

    def _handle_chat(self, user_id: str, room_id: str, msg: Dict[str, Any]) -> None:
        """Validates and broadcasts a group chat message."""
        client = self.connection_mgr.get_client(user_id)
        username = client.username if client else "User"
        text = msg.get("text", "")

        chat = self.chat_mgr.get_or_create_room_chat(room_id)
        success, reason, chat_msg = chat.add_message(user_id, username, text)

        if not success or not chat_msg:
            self.connection_mgr.send_to_client(
                user_id,
                build_message(MessageType.ERROR, message=f"Chat failed: {reason}"),
            )
            return

        tracker = self.report_mgr.get_tracker(room_id)
        if tracker:
            tracker.record_chat(user_id, chat_msg.text)

        broadcast_msg = build_message(
            MessageType.CHAT,
            room_id=room_id,
            message_id=chat_msg.message_id,
            user_id=user_id,
            username=username,
            text=chat_msg.text,
            timestamp=chat_msg.timestamp,
        )
        self.connection_mgr.broadcast_to_room(room_id, broadcast_msg)

    def _monitor_loop(self) -> None:
        """Periodic background monitor for timeouts and persistence."""
        last_persist_time = time.time()

        while self._is_running:
            time.sleep(2.0)
            now = time.time()

            # 1. Check inactive clients
            inactive_uids = self.connection_mgr.get_inactive_clients(self.config.ping_timeout)
            for uid in inactive_uids:
                logger.warning("Client %s timed out due to inactivity", uid)
                client = self.connection_mgr.get_client(uid)
                if client and client.room_id:
                    self._handle_leave_room(uid, client.room_id)
                self.connection_mgr.unregister_client(uid)

            # 2. Periodic persistence every 10 seconds
            if (now - last_persist_time) >= 10.0:
                last_persist_time = now
                for room_info in self.session_mgr.list_rooms():
                    room = self.session_mgr.get_room(room_info["room_id"])
                    if room:
                        self.persistence_mgr.save_room_state(room, self.whiteboard_mgr, self.chat_mgr)
