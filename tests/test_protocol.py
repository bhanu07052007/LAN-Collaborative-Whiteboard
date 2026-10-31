"""
Unit tests for Network Communication Protocol and Length-Prefixed Framing.
Tests TCP byte streaming, partial reads, multi-message streams, and error handling.
"""

import json
import socket
import struct
import sys
import threading
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pytest
except ImportError:
    import contextlib

    class _PytestFallback:
        @staticmethod
        @contextlib.contextmanager
        def raises(exc):
            try:
                yield
            except exc:
                pass
            else:
                raise AssertionError(f"Expected {exc.__name__} was not raised")

    pytest = _PytestFallback()

from common.constants import HEADER_SIZE, MAX_MESSAGE_SIZE
from common.message_types import MessageType
from common.protocol import (
    InvalidMessageError,
    MessageFramingError,
    build_message,
    pack_message,
    receive_message,
    recv_exact,
    send_message,
    unpack_header,
    validate_message,
)


def create_connected_socket_pair():
    """Helper to create a connected pair of IPv4 TCP sockets for testing."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    conn, _ = server.accept()
    server.close()
    return client, conn


def test_pack_unpack_header():
    """Verify 4-byte big-endian unsigned integer packing and unpacking."""
    test_lengths = [0, 1, 100, 65535, 1024 * 1024]
    for length in test_lengths:
        header = struct.pack("!I", length)
        assert len(header) == HEADER_SIZE
        assert unpack_header(header) == length

    # Header with invalid length exceeding max
    excessive_header = struct.pack("!I", MAX_MESSAGE_SIZE + 100)
    with pytest.raises(MessageFramingError):
        unpack_header(excessive_header)


def test_pack_message_valid():
    """Verify that pack_message serializes dictionary to length-prefixed bytes."""
    msg = {"type": "TEST", "value": 42, "text": "hello"}
    packed = pack_message(msg)

    # First 4 bytes length
    length = struct.unpack("!I", packed[:4])[0]
    payload = packed[4:]
    assert len(payload) == length
    decoded = json.loads(payload.decode("utf-8"))
    assert decoded["type"] == "TEST"
    assert decoded["value"] == 42


def test_send_and_receive_over_socket():
    """Tests basic send and receive over a real TCP socket pair."""
    s1, s2 = create_connected_socket_pair()
    try:
        msg = build_message(MessageType.PING)
        send_message(s1, msg)

        received = receive_message(s2)
        assert received is not None
        assert received["type"] == MessageType.PING.value
        assert "timestamp" in received
    finally:
        s1.close()
        s2.close()


def test_partial_tcp_reads():
    """
    Simulates network fragmentation where TCP segments arrive in small byte chunks.
    Verifies that recv_exact reassembles the full message without loss.
    """
    s1, s2 = create_connected_socket_pair()
    try:
        msg = {
            "type": MessageType.DRAW.value,
            "room_id": "test-room",
            "points": [[i, i * 2] for i in range(100)],
        }
        packet = pack_message(msg)

        # Thread sending message 5 bytes at a time with tiny sleeps
        def trickle_send():
            chunk_size = 7
            for i in range(0, len(packet), chunk_size):
                s1.sendall(packet[i : i + chunk_size])

        sender_t = threading.Thread(target=trickle_send)
        sender_t.start()

        # Receiver should gather all chunks correctly
        received = receive_message(s2)
        sender_t.join()

        assert received is not None
        assert received["type"] == MessageType.DRAW.value
        assert len(received["points"]) == 100
    finally:
        s1.close()
        s2.close()


def test_multiple_messages_in_stream():
    """
    Simulates TCP stream aggregation where multiple messages arrive back-to-back.
    Verifies that receive_message accurately unpacks each in order.
    """
    s1, s2 = create_connected_socket_pair()
    try:
        msg1 = {"type": "MSG1", "index": 1}
        msg2 = {"type": "MSG2", "index": 2}
        msg3 = {"type": "MSG3", "index": 3}

        # Send all 3 messages rapidly in one combined write
        packet_all = pack_message(msg1) + pack_message(msg2) + pack_message(msg3)
        s1.sendall(packet_all)

        r1 = receive_message(s2)
        r2 = receive_message(s2)
        r3 = receive_message(s2)

        assert r1["type"] == "MSG1" and r1["index"] == 1
        assert r2["type"] == "MSG2" and r2["index"] == 2
        assert r3["type"] == "MSG3" and r3["index"] == 3
    finally:
        s1.close()
        s2.close()


def test_clean_eof_detection():
    """Verifies that closing connection returns None indicating EOF."""
    s1, s2 = create_connected_socket_pair()
    try:
        s1.close()
        res = receive_message(s2)
        assert res is None
    finally:
        s2.close()


def test_invalid_json_handling():
    """Verifies that malformed payload raises InvalidMessageError."""
    s1, s2 = create_connected_socket_pair()
    try:
        bad_payload = b"not a valid json {{"
        header = struct.pack("!I", len(bad_payload))
        s1.sendall(header + bad_payload)

        with pytest.raises(InvalidMessageError):
            receive_message(s2)
    finally:
        s1.close()
        s2.close()


def test_validate_message():
    """Tests validation of message schemas."""
    is_valid, _ = validate_message({"type": MessageType.DRAW.value})
    assert is_valid

    is_valid, _ = validate_message({"type": "UNKNOWN_TYPE"})
    assert not is_valid

    is_valid, _ = validate_message("not a dict")
    assert not is_valid
