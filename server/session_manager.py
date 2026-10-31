"""
Session Manager for LAN Collaborative Whiteboard Server.
Handles whiteboard room lifecycles, access control (passwords), and participant membership.
Maintains room-level state isolation.
"""

import hashlib
import logging
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from common.constants import (
    MAX_PASSWORD_LEN,
    MAX_ROOM_ID_LEN,
    MAX_USERNAME_LEN,
    MIN_ROOM_ID_LEN,
    MIN_USERNAME_LEN,
    USER_PALETTE,
)

logger = logging.getLogger("SessionManager")


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hashes a password with SHA-256 and a random salt."""
    if not salt:
        salt = secrets.token_hex(8)
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return h, salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verifies a plain-text password against the stored hash and salt."""
    h, _ = hash_password(password, salt)
    return secrets.compare_digest(h, password_hash)


@dataclass
class Participant:
    user_id: str
    username: str
    color: str
    joined_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "color": self.color,
            "joined_at": self.joined_at,
        }


@dataclass
class Room:
    room_id: str
    room_name: str
    creator_id: str
    created_at: float = field(default_factory=time.time)
    password_hash: Optional[str] = None
    password_salt: Optional[str] = None
    participants: Dict[str, Participant] = field(default_factory=dict)
    palette_index: int = 0
    lock: threading.RLock = field(default_factory=threading.RLock)

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    def get_next_color(self) -> str:
        color = USER_PALETTE[self.palette_index % len(USER_PALETTE)]
        self.palette_index += 1
        return color

    def add_participant(self, user_id: str, username: str, requested_color: Optional[str] = None) -> Participant:
        with self.lock:
            color = requested_color if requested_color else self.get_next_color()
            # If user already exists in room, update details
            participant = Participant(user_id=user_id, username=username, color=color)
            self.participants[user_id] = participant
            return participant

    def remove_participant(self, user_id: str) -> Optional[Participant]:
        with self.lock:
            return self.participants.pop(user_id, None)

    def get_participant(self, user_id: str) -> Optional[Participant]:
        with self.lock:
            return self.participants.get(user_id)

    def list_participants(self) -> List[Dict[str, Any]]:
        with self.lock:
            res = []
            for p in self.participants.values():
                d = p.to_dict()
                d["is_host"] = (p.user_id == self.creator_id)
                res.append(d)
            return res

    def is_username_taken(self, username: str, exclude_user_id: Optional[str] = None) -> bool:
        with self.lock:
            for uid, p in self.participants.items():
                if uid != exclude_user_id and p.username.lower() == username.lower():
                    return True
            return False

    def to_dict(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "room_id": self.room_id,
                "room_name": self.room_name,
                "creator_id": self.creator_id,
                "created_at": self.created_at,
                "has_password": self.has_password,
                "password_hash": self.password_hash,
                "password_salt": self.password_salt,
                "participants": [p.to_dict() for p in self.participants.values()],
            }


class SessionManager:
    def __init__(self) -> None:
        self._rooms: Dict[str, Room] = {}
        self._lock = threading.RLock()

    def create_room(
        self,
        room_id: str,
        creator_id: str,
        room_name: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Room]]:
        """
        Creates a new whiteboard room.
        Returns (success, message, room_instance).
        """
        clean_id = room_id.strip()
        if not (MIN_ROOM_ID_LEN <= len(clean_id) <= MAX_ROOM_ID_LEN):
            return False, f"Room ID must be between {MIN_ROOM_ID_LEN} and {MAX_ROOM_ID_LEN} characters", None

        # Sanitize room ID
        if not clean_id.replace("-", "").replace("_", "").isalnum():
            return False, "Room ID may only contain alphanumeric characters, hyphens, and underscores", None

        clean_name = (room_name or clean_id).strip()[:64]

        pwd_hash = None
        pwd_salt = None
        if password and len(password.strip()) > 0:
            if len(password) > MAX_PASSWORD_LEN:
                return False, f"Password exceeds {MAX_PASSWORD_LEN} characters", None
            pwd_hash, pwd_salt = hash_password(password)

        with self._lock:
            if clean_id in self._rooms:
                return False, f"Room '{clean_id}' already exists", None

            room = Room(
                room_id=clean_id,
                room_name=clean_name,
                creator_id=creator_id,
                password_hash=pwd_hash,
                password_salt=pwd_salt,
            )
            self._rooms[clean_id] = room
            logger.info("Created room '%s' (%s) by user %s", clean_name, clean_id, creator_id)
            return True, "Room created successfully", room

    def join_room(
        self,
        room_id: str,
        user_id: str,
        username: str,
        password: Optional[str] = None,
        user_color: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Participant], Optional[Room]]:
        """
        Validates access and joins a user to an existing room.
        Returns (success, message, participant, room).
        """
        clean_username = username.strip()
        if not (MIN_USERNAME_LEN <= len(clean_username) <= MAX_USERNAME_LEN):
            return False, f"Username must be between {MIN_USERNAME_LEN} and {MAX_USERNAME_LEN} characters", None, None

        with self._lock:
            room = self._rooms.get(room_id)
            if not room:
                return False, f"Room '{room_id}' not found", None, None

            # Check password if room is protected
            if room.has_password:
                if not password:
                    return False, "This room requires a password", None, None
                if not room.password_salt or not room.password_hash or not verify_password(password, room.password_hash, room.password_salt):
                    return False, "Incorrect room password", None, None

            # Check for duplicate username in this room
            if room.is_username_taken(clean_username, exclude_user_id=user_id):
                # Auto-disambiguate username if needed
                candidate = clean_username
                counter = 2
                while room.is_username_taken(candidate, exclude_user_id=user_id):
                    candidate = f"{clean_username} ({counter})"
                    counter += 1
                clean_username = candidate

            participant = room.add_participant(user_id, clean_username, user_color)
            logger.info("User %s (%s) joined room %s", clean_username, user_id, room_id)
            return True, "Joined room successfully", participant, room

    def leave_room(self, room_id: str, user_id: str) -> Tuple[bool, Optional[Participant]]:
        """Removes a user from a room."""
        with self._lock:
            room = self._rooms.get(room_id)
            if not room:
                return False, None
            part = room.remove_participant(user_id)
            if part:
                logger.info("User %s left room %s", part.username, room_id)
            return True, part

    def get_room(self, room_id: str) -> Optional[Room]:
        with self._lock:
            return self._rooms.get(room_id)

    def list_rooms(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "room_id": r.room_id,
                    "room_name": r.room_name,
                    "has_password": r.has_password,
                    "participants_count": len(r.participants),
                }
                for r in self._rooms.values()
            ]

    def register_restored_room(self, room: Room) -> None:
        """Registers a room restored from persistent storage."""
        with self._lock:
            self._rooms[room.room_id] = room
            logger.info("Restored room %s into SessionManager", room.room_id)
