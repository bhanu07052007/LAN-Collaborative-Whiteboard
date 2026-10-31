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
