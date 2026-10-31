"""
Chat Manager for LAN Collaborative Whiteboard Server.
Handles validation, formatting, timestamping, and in-memory history of chat messages per room.
"""

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from common.constants import MAX_CHAT_LEN

logger = logging.getLogger("ChatManager")


@dataclass
class ChatMessage:
    message_id: str
    room_id: str
    user_id: str
    username: str
    text: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "room_id": self.room_id,
            "user_id": self.user_id,
            "username": self.username,
            "text": self.text,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ChatMessage":
        return cls(
            message_id=d["message_id"],
            room_id=d["room_id"],
            user_id=d["user_id"],
            username=d["username"],
            text=d["text"],
            timestamp=d.get("timestamp", time.time()),
        )


class RoomChat:
    """Manages chat messages for an individual room."""

    def __init__(self, room_id: str, max_history: int = 500) -> None:
        self.room_id = room_id
        self.max_history = max_history
        self._history: List[ChatMessage] = []
        self._counter = 0
        self._lock = threading.RLock()

    def add_message(self, user_id: str, username: str, text: str) -> Tuple[bool, str, Optional[ChatMessage]]:
        """Validates and stores a new chat message."""
        clean_text = text.strip()
        if not clean_text:
            return False, "Chat message cannot be empty", None

        if len(clean_text) > MAX_CHAT_LEN:
            return False, f"Message exceeds maximum length of {MAX_CHAT_LEN} characters", None

        with self._lock:
            self._counter += 1
            msg_id = f"msg-{int(time.time()*1000)}-{self._counter}"
            msg = ChatMessage(
                message_id=msg_id,
                room_id=self.room_id,
                user_id=user_id,
                username=username,
                text=clean_text,
            )
            self._history.append(msg)
            if len(self._history) > self.max_history:
                self._history.pop(0)

            return True, "", msg

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return [m.to_dict() for m in self._history[-limit:]]

    def load_history(self, messages_data: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._history = [ChatMessage.from_dict(d) for d in messages_data]
            self._counter = len(self._history)


class ChatManager:
    """Global manager orchestrating chat across all rooms."""

    def __init__(self) -> None:
        self._rooms: Dict[str, RoomChat] = {}
        self._lock = threading.RLock()

    def get_or_create_room_chat(self, room_id: str) -> RoomChat:
        with self._lock:
            if room_id not in self._rooms:
                self._rooms[room_id] = RoomChat(room_id)
            return self._rooms[room_id]

    def get_room_chat(self, room_id: str) -> Optional[RoomChat]:
        with self._lock:
            return self._rooms.get(room_id)
