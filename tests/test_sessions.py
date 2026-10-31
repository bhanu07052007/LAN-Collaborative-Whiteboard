"""
Unit tests for Session Manager, Room Lifecycles, and Access Control.
Tests room creation, password verification, participant tracking, and username disambiguation.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pytest
except ImportError:
    pytest = None

from server.session_manager import Room, SessionManager, hash_password, verify_password


def test_password_hashing_and_verification():
    pwd = "SecretPassword123!"
    h, salt = hash_password(pwd)
    assert h != pwd
    assert len(salt) > 0
    assert verify_password(pwd, h, salt)
    assert not verify_password("WrongPassword", h, salt)


def test_create_room():
    sm = SessionManager()

    # Valid creation
    ok, msg, room = sm.create_room("sprint-1", "user-1", "Sprint 1 Board")
    assert ok
    assert room is not None
    assert room.room_id == "sprint-1"
    assert not room.has_password

    # Duplicate room ID
    ok2, msg2, room2 = sm.create_room("sprint-1", "user-2")
    assert not ok2
    assert "already exists" in msg2

    # Invalid room ID (contains spaces or invalid symbols)
    ok3, msg3, _ = sm.create_room("bad id with spaces!", "user-3")
    assert not ok3


def test_password_protected_room():
    sm = SessionManager()
    ok, _, room = sm.create_room("secure-room", "host-1", password="StrongPassword")
    assert ok
    assert room.has_password

    # Attempt join without password
    ok_j1, msg_j1, _, _ = sm.join_room("secure-room", "u2", "Bob")
    assert not ok_j1
    assert "requires a password" in msg_j1

    # Attempt join with wrong password
    ok_j2, msg_j2, _, _ = sm.join_room("secure-room", "u2", "Bob", password="Incorrect")
    assert not ok_j2
    assert "Incorrect" in msg_j2

    # Join with correct password
    ok_j3, msg_j3, part, r = sm.join_room("secure-room", "u2", "Bob", password="StrongPassword")
    assert ok_j3
    assert part is not None
    assert part.username == "Bob"


def test_username_disambiguation():
    sm = SessionManager()
    sm.create_room("collab", "host")

    # First user joins as 'Alice'
    sm.join_room("collab", "u1", "Alice")

    # Second user tries to join as 'Alice' -> auto-renamed to 'Alice (2)'
    ok, _, part2, _ = sm.join_room("collab", "u2", "Alice")
    assert ok
    assert part2.username == "Alice (2)"

    # Third user also named 'Alice' -> 'Alice (3)'
    ok3, _, part3, _ = sm.join_room("collab", "u3", "Alice")
    assert ok3
    assert part3.username == "Alice (3)"


def test_participant_leave():
    sm = SessionManager()
    sm.create_room("meeting", "host")
    sm.join_room("meeting", "u1", "Charlie")

    room = sm.get_room("meeting")
    assert len(room.participants) == 1

    ok, left_part = sm.leave_room("meeting", "u1")
    assert ok
    assert left_part.username == "Charlie"
    assert len(room.participants) == 0
