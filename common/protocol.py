"""
Network Communication Protocol for Collaborative Whiteboard.
Implements length-prefixed framing over TCP:
- 4 bytes unsigned big-endian length prefix (!I)
- UTF-8 JSON payload
Provides robust socket message sending and receiving with partial-read handling.
"""

import json
import logging
import socket
import struct
import time
from typing import Any, Dict, Optional, Tuple

from common.constants import HEADER_SIZE, MAX_MESSAGE_SIZE
from common.message_types import MessageType, VALID_MESSAGE_TYPES

logger = logging.getLogger("Protocol")


class ProtocolError(Exception):
    """Base exception for protocol-related errors."""
    pass


class MessageFramingError(ProtocolError):
    """Raised when message framing fails (e.g. invalid length)."""
    pass


class InvalidMessageError(ProtocolError):
    """Raised when JSON decoding or validation fails."""
    pass


def pack_message(message_dict: Dict[str, Any]) -> bytes:
    """
    Serializes a message dictionary to UTF-8 JSON and prepends
    a 4-byte unsigned big-endian length header.
    """
    try:
        payload_bytes = json.dumps(message_dict, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as e:
        raise InvalidMessageError(f"Failed to serialize message to JSON: {e}") from e

    length = len(payload_bytes)
    if length > MAX_MESSAGE_SIZE:
        raise MessageFramingError(f"Message size {length} bytes exceeds MAX_MESSAGE_SIZE ({MAX_MESSAGE_SIZE})")

    header = struct.pack("!I", length)
    return header + payload_bytes


def unpack_header(header_bytes: bytes) -> int:
    """
    Unpacks 4-byte big-endian header into an integer length.
    """
    if len(header_bytes) != HEADER_SIZE:
        raise MessageFramingError(f"Header must be {HEADER_SIZE} bytes, got {len(header_bytes)}")
    length: int = struct.unpack("!I", header_bytes)[0]
    if length > MAX_MESSAGE_SIZE:
        raise MessageFramingError(f"Incoming message declared size {length} bytes exceeds max {MAX_MESSAGE_SIZE}")
    return length


def recv_exact(sock: socket.socket, num_bytes: int) -> Optional[bytes]:
    """
    Reads exactly num_bytes from the TCP socket.
    Handles partial TCP reads by looping until all requested bytes are gathered.
    Returns:
        bytes: If exactly num_bytes were read.
        None: If connection closed cleanly (EOF) before any bytes were received.
    Raises:
        ConnectionResetError: If connection closed prematurely during a read.
        socket.timeout: If socket timeout triggers.
        OSError: For other socket errors.
    """
    buffer = bytearray()
    while len(buffer) < num_bytes:
        bytes_needed = num_bytes - len(buffer)
        try:
            chunk = sock.recv(bytes_needed)
        except socket.timeout:
            # Re-raise socket.timeout to allow callers to handle keepalive/ping
            raise
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError) as e:
            if len(buffer) == 0:
                return None
            raise ConnectionResetError(f"Socket disconnected during read ({len(buffer)}/{num_bytes} bytes): {e}") from e
        except OSError as e:
            raise OSError(f"Socket error reading {bytes_needed} bytes: {e}") from e

        if not chunk:
            # Clean EOF if nothing read yet
            if len(buffer) == 0:
                return None
            # Incomplete message before connection closed
            raise ConnectionResetError(f"Connection closed prematurely, expected {num_bytes} bytes, received {len(buffer)}")

        buffer.extend(chunk)

    return bytes(buffer)


def send_message(sock: socket.socket, message_dict: Dict[str, Any]) -> None:
    """
    Frames and sends a message dictionary over the socket.
    Uses sendall to guarantee full transmission.
    """
    packet = pack_message(message_dict)
    try:
        sock.sendall(packet)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
        raise ConnectionResetError(f"Failed to send message over socket: {e}") from e
    except OSError as e:
        raise OSError(f"Socket error while sending message: {e}") from e


def receive_message(sock: socket.socket) -> Optional[Dict[str, Any]]:
    """
    Receives a single complete length-prefixed JSON message from the socket.
    Returns:
        dict: The decoded JSON message.
        None: If the peer closed connection cleanly (EOF).
    Raises:
        ProtocolError: On invalid framing or unparseable JSON.
        ConnectionResetError: On unexpected connection loss.
        socket.timeout: When socket read times out.
    """
    # 1. Read 4-byte length prefix
    header = recv_exact(sock, HEADER_SIZE)
    if header is None:
        return None  # Connection cleanly closed by peer

    payload_length = unpack_header(header)
    if payload_length == 0:
        return {}

    # 2. Read exact payload
    payload_bytes = recv_exact(sock, payload_length)
    if payload_bytes is None:
        raise ConnectionResetError("Connection closed while reading message payload")

    # 3. Decode UTF-8 and parse JSON
    try:
        text = payload_bytes.decode("utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise InvalidMessageError(f"Message payload must be a JSON object, got {type(data).__name__}")
        return data
    except UnicodeDecodeError as e:
        raise InvalidMessageError(f"UTF-8 decoding failed for payload: {e}") from e
    except json.JSONDecodeError as e:
        raise InvalidMessageError(f"JSON parsing failed for payload: {e}") from e


# Message Builder Helpers
def build_message(msg_type: MessageType | str, **kwargs: Any) -> Dict[str, Any]:
    """Helper to construct standardized messages with a timestamp."""
    msg = {"type": str(msg_type)}
    msg.update(kwargs)
    if "timestamp" not in msg:
        msg["timestamp"] = time.time()
    return msg


def validate_message(msg: Any) -> Tuple[bool, str]:
    """
    Validates that a message dictionary contains a valid 'type' field.
    Returns (is_valid, error_reason).
    """
    if not isinstance(msg, dict):
        return False, "Message must be a dictionary"
    msg_type = msg.get("type")
    if not msg_type or not isinstance(msg_type, str):
        return False, "Missing or invalid 'type' field in message"
    if msg_type not in VALID_MESSAGE_TYPES:
        return False, f"Unknown message type '{msg_type}'"
    return True, ""
