"""
End-to-End Integration tests for SocketServer, Multi-Client TCP Networking,
Broadcasting, Whiteboard Synchronization, Chat, and Lifecycle Management.
"""

import socket
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pytest
except ImportError:
    pytest = None

from common.constants import TOOL_PEN
from common.message_types import MessageType
from common.protocol import build_message, receive_message, send_message
from server.server_config import ServerConfig
from server.socket_server import SocketServer


def get_ephemeral_port() -> int:
    """Finds an unused local port to avoid collision during parallel test runs."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_full_server_client_integration():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        port = get_ephemeral_port()
        config = ServerConfig(host="127.0.0.1", port=port, sessions_dir=Path(tmpdir))
        server = SocketServer(config)
        server.start()
        time.sleep(0.3)  # Allow socket to bind and listen

        c1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            # 1. Client 1 connects and creates a room
            c1.connect(("127.0.0.1", port))
            create_msg = build_message(
                MessageType.CREATE_ROOM,
                room_id="integ-room",
                room_name="Integration Room",
                username="Alice",
                user_id="user-alice",
            )
            send_message(c1, create_msg)

            r1 = receive_message(c1)
            assert r1 is not None
            assert r1["type"] == MessageType.ROOM_CREATED.value
            assert r1["room_id"] == "integ-room"
            assert len(r1["participants"]) == 1

            # 2. Client 2 connects and joins the room
            c2.connect(("127.0.0.1", port))
            join_msg = build_message(
                MessageType.JOIN_ROOM,
                room_id="integ-room",
                username="Bob",
                user_id="user-bob",
            )
            send_message(c2, join_msg)

            # Client 2 should receive JOIN_SUCCESS
            r2 = receive_message(c2)
            assert r2 is not None
            assert r2["type"] == MessageType.JOIN_SUCCESS.value
            assert len(r2["participants"]) == 2

            # Client 1 should receive PARTICIPANT_JOINED notification
            c1_notify = receive_message(c1)
            assert c1_notify is not None
            assert c1_notify["type"] == MessageType.PARTICIPANT_JOINED.value
            assert c1_notify["username"] == "Bob"

            # 3. Client 1 draws on whiteboard
            draw_op = {
                "type": MessageType.DRAW.value,
                "room_id": "integ-room",
                "op_type": TOOL_PEN,
                "data": {
                    "points": [[10, 10], [20, 20]],
                    "color": "#3B82F6",
                    "width": 3,
                },
            }
            send_message(c1, draw_op)

            # Client 1 receives OP_ACK then STATE_UPDATE; Client 2 receives STATE_UPDATE
            upd1 = receive_message(c1)
            if upd1.get("type") == MessageType.OP_ACK.value:
                assert upd1.get("status") == "accepted"
                upd1 = receive_message(c1)

            upd2 = receive_message(c2)
            assert upd1["type"] == MessageType.STATE_UPDATE.value
            assert upd2["type"] == MessageType.STATE_UPDATE.value
            assert upd1["seq_num"] == 1
            assert upd2["seq_num"] == 1
            assert upd1["operation"]["username"] == "Alice"

            # 4. Client 2 sends a chat message
            chat_msg = build_message(
                MessageType.CHAT,
                room_id="integ-room",
                text="Hello Alice!",
            )
            send_message(c2, chat_msg)

            chat1 = receive_message(c1)
            chat2 = receive_message(c2)
            assert chat1["type"] == MessageType.CHAT.value
            assert chat2["type"] == MessageType.CHAT.value
            assert chat1["text"] == "Hello Alice!"
            assert chat1["username"] == "Bob"

            # 5. Client 1 sends UNDO
            undo_msg = build_message(MessageType.UNDO, room_id="integ-room")
            send_message(c1, undo_msg)

            undo1 = receive_message(c1)
            undo2 = receive_message(c2)
            assert undo1["type"] == MessageType.STATE_UPDATE.value
            assert undo1["action"] == "undo"
            assert undo2["action"] == "undo"

            # 6. Heartbeat test: Client 1 sends PING -> receives PONG
            send_message(c1, build_message(MessageType.PING))
            pong = receive_message(c1)
            assert pong["type"] == MessageType.PONG.value

            # 7. Client 2 disconnects -> Client 1 receives PARTICIPANT_LEFT
            c2.close()
            left_notify = receive_message(c1)
            assert left_notify is not None
            assert left_notify["type"] == MessageType.PARTICIPANT_LEFT.value
            assert left_notify["username"] == "Bob"

        finally:
            try:
                c1.close()
            except Exception:
                pass
            try:
                c2.close()
            except Exception:
                pass
            server.stop()


def test_two_client_undo_redo_and_clear_synchronization():
    """
    Direct multi-client TCP integration test covering the 10-step synchronization requirement:
    1. Host draws something.
    2. Participant draws something.
    3. Host performs Undo.
    4. Verify that the correct operation disappears on all clients.
    5. Host performs Redo.
    6. Verify that the operation returns on all clients.
    7. Participant attempts to clear the canvas.
    8. Verify that the server rejects the request.
    9. Host clears the canvas.
    10. Verify that the canvas becomes empty on both clients.
    """
    def recv_match(sock, msg_type, action=None, timeout=3.0):
        start = time.time()
        sock.settimeout(timeout)
        while time.time() - start < timeout:
            m = receive_message(sock)
            if m and m.get("type") == msg_type:
                if action is None or m.get("action") == action:
                    return m
        return None

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        port = get_ephemeral_port()
        config = ServerConfig(host="127.0.0.1", port=port, sessions_dir=Path(tmpdir))
        server = SocketServer(config)
        server.start()
        time.sleep(0.3)

        c_host = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c_part = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            # Setup: Host creates room, Participant joins
            c_host.connect(("127.0.0.1", port))
            send_message(c_host, build_message(
                MessageType.CREATE_ROOM,
                room_id="sync-test-room",
                room_name="Sync Test Room",
                username="HostUser",
                user_id="user-host",
            ))
            r_host = receive_message(c_host)
            assert r_host["type"] == MessageType.ROOM_CREATED.value
            assert r_host["is_host"] is True

            c_part.connect(("127.0.0.1", port))
            send_message(c_part, build_message(
                MessageType.JOIN_ROOM,
                room_id="sync-test-room",
                username="RemotePart",
                user_id="user-part",
            ))
            r_part = receive_message(c_part)
            assert r_part["type"] == MessageType.JOIN_SUCCESS.value
            assert r_part["is_host"] is False

            # Drain join notice from host
            recv_match(c_host, MessageType.PARTICIPANT_JOINED.value)

            # 1. Host draws something (rectangle)
            host_rect_op = {
                "type": MessageType.DRAW.value,
                "room_id": "sync-test-room",
                "op_type": "rect",
                "data": {"start": [10, 10], "end": [50, 50], "color": "#000000", "width": 2},
                "op_id": "op-host-rect",
            }
            send_message(c_host, host_rect_op)
            upd_host_1 = recv_match(c_host, MessageType.STATE_UPDATE.value, action="draw")
            upd_part_1 = recv_match(c_part, MessageType.STATE_UPDATE.value, action="draw")
            assert (upd_host_1.get("op_id") or upd_host_1.get("operation", {}).get("op_id")) == "op-host-rect"
            assert (upd_part_1.get("op_id") or upd_part_1.get("operation", {}).get("op_id")) == "op-host-rect"

            # 2. Participant draws something (line)
            part_line_op = {
                "type": MessageType.DRAW.value,
                "room_id": "sync-test-room",
                "op_type": "line",
                "data": {"start": [100, 100], "end": [200, 200], "color": "#FF0000", "width": 3},
                "op_id": "op-part-line",
            }
            send_message(c_part, part_line_op)
            upd_host_2 = recv_match(c_host, MessageType.STATE_UPDATE.value, action="draw")
            upd_part_2 = recv_match(c_part, MessageType.STATE_UPDATE.value, action="draw")
            assert (upd_host_2.get("op_id") or upd_host_2.get("operation", {}).get("op_id")) == "op-part-line"
            assert (upd_part_2.get("op_id") or upd_part_2.get("operation", {}).get("op_id")) == "op-part-line"

            # 3. Host performs Undo
            send_message(c_host, build_message(MessageType.UNDO, room_id="sync-test-room"))

            # 4. Verify that the correct operation disappears on all clients (host's rect undone, participant's line untouched)
            undo_host = recv_match(c_host, MessageType.STATE_UPDATE.value, action="undo")
            undo_part = recv_match(c_part, MessageType.STATE_UPDATE.value, action="undo")
            assert undo_host is not None and undo_part is not None
            assert undo_host["op_id"] == "op-host-rect"
            assert undo_part["op_id"] == "op-host-rect"
            assert undo_host["operation"]["is_undone"] is True
            assert undo_part["operation"]["is_undone"] is True

            # 5. Host performs Redo
            send_message(c_host, build_message(MessageType.REDO, room_id="sync-test-room"))

            # 6. Verify that the operation returns on all clients (host's rect restored)
            redo_host = recv_match(c_host, MessageType.STATE_UPDATE.value, action="redo")
            redo_part = recv_match(c_part, MessageType.STATE_UPDATE.value, action="redo")
            assert redo_host is not None and redo_part is not None
            assert redo_host["op_id"] == "op-host-rect"
            assert redo_part["op_id"] == "op-host-rect"
            assert redo_host["operation"]["is_undone"] is False
            assert redo_part["operation"]["is_undone"] is False

            # 6b. Participant performs Undo (verifying participant can undo their line without affecting host's rect)
            send_message(c_part, build_message(MessageType.UNDO, room_id="sync-test-room"))
            p_undo_host = recv_match(c_host, MessageType.STATE_UPDATE.value, action="undo")
            p_undo_part = recv_match(c_part, MessageType.STATE_UPDATE.value, action="undo")
            assert p_undo_host is not None and p_undo_part is not None
            assert p_undo_host["op_id"] == "op-part-line"
            assert p_undo_part["op_id"] == "op-part-line"
            assert p_undo_host["operation"]["is_undone"] is True
            assert p_undo_part["operation"]["is_undone"] is True

            # 6c. Participant performs Redo (verifying participant restores their line)
            send_message(c_part, build_message(MessageType.REDO, room_id="sync-test-room"))
            p_redo_host = recv_match(c_host, MessageType.STATE_UPDATE.value, action="redo")
            p_redo_part = recv_match(c_part, MessageType.STATE_UPDATE.value, action="redo")
            assert p_redo_host is not None and p_redo_part is not None
            assert p_redo_host["op_id"] == "op-part-line"
            assert p_redo_part["op_id"] == "op-part-line"
            assert p_redo_host["operation"]["is_undone"] is False
            assert p_redo_part["operation"]["is_undone"] is False

            # 7. Participant attempts to clear the canvas (unauthorized)
            send_message(c_part, build_message(MessageType.CLEAR_CANVAS, room_id="sync-test-room"))

            # 8. Verify that the server rejects the request
            err_part = recv_match(c_part, MessageType.ERROR.value)
            assert err_part is not None
            assert "Only the meeting host" in err_part["message"]

            # 9. Host clears the canvas
            send_message(c_host, build_message(MessageType.CLEAR_CANVAS, room_id="sync-test-room"))

            # 10. Verify that the canvas becomes empty on both clients
            clear_host = recv_match(c_host, MessageType.CLEAR_CANVAS.value)
            clear_part = recv_match(c_part, MessageType.CLEAR_CANVAS.value)
            assert clear_host is not None
            assert clear_part is not None
            assert clear_host["username"] == "HostUser"
            assert clear_part["username"] == "HostUser"

        finally:
            try:
                c_host.close()
            except Exception:
                pass
            try:
                c_part.close()
            except Exception:
                pass
            server.stop()

