"""
Persistence Manager for LAN Collaborative Whiteboard Server.
Handles saving and restoring room configurations, drawing operations, and chat history.
Uses atomic JSON writes to guarantee data integrity across server restarts.
"""

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from server.chat_manager import ChatManager
from server.session_manager import Room, SessionManager
from server.whiteboard_manager import WhiteboardManager

logger = logging.getLogger("PersistenceManager")


class PersistenceManager:
    def __init__(self, sessions_dir: Path) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()

    def _get_room_file(self, room_id: str) -> Path:
        safe_id = "".join(c for c in room_id if c.isalnum() or c in ("-", "_"))
        return self.sessions_dir / f"{safe_id}.json"

    def save_room_state(
        self,
        room: Room,
        whiteboard_mgr: WhiteboardManager,
        chat_mgr: ChatManager,
    ) -> bool:
        """
        Atomically saves complete room state (metadata, drawing ops, chat) to JSON.
        Uses unique temp file and retry backoff for Windows file locking compatibility.
        """
        with self._write_lock:
            file_path = self._get_room_file(room.room_id)
            temp_path = file_path.with_name(f"{file_path.stem}_{uuid.uuid4().hex[:6]}.tmp")

            wb = whiteboard_mgr.get_room_whiteboard(room.room_id)
            chat = chat_mgr.get_room_chat(room.room_id)

            data: Dict[str, Any] = {
                "version": 1,
                "room_id": room.room_id,
                "room_name": room.room_name,
                "creator_id": room.creator_id,
                "created_at": room.created_at,
                "has_password": room.has_password,
                "password_hash": room.password_hash,
                "password_salt": room.password_salt,
                "seq_num": wb.current_seq_num if wb else 0,
                "operations": wb.get_full_history() if wb else [],
                "chat_messages": chat.get_history(limit=500) if chat else [],
            }

            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # Windows retry loop for atomic replace
                for attempt in range(4):
                    try:
                        temp_path.replace(file_path)
                        logger.debug("Successfully saved state for room %s to %s", room.room_id, file_path)
                        return True
                    except OSError:
                        if attempt < 3:
                            time.sleep(0.05)
                        else:
                            raise
                return False
            except Exception as e:
                logger.debug("Notice saving state for room %s: %s", room.room_id, e)
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
                return False

    def load_room_state(self, room_id: str) -> Optional[Dict[str, Any]]:
        """Reads persisted room state from JSON file."""
        file_path = self._get_room_file(room_id)
        if not file_path.is_file():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load room file %s: %s", file_path, e)
            return None

    def restore_all_rooms(
        self,
        session_mgr: SessionManager,
        whiteboard_mgr: WhiteboardManager,
        chat_mgr: ChatManager,
    ) -> int:
        """
        Restores all saved rooms on server startup.
        Returns the number of rooms restored.
        """
        restored = 0
        for p in self.sessions_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)

                room_id = data.get("room_id")
                if not room_id:
                    continue

                room = Room(
                    room_id=room_id,
                    room_name=data.get("room_name", room_id),
                    creator_id=data.get("creator_id", "system"),
                    created_at=data.get("created_at", 0),
                    password_hash=data.get("password_hash"),
                    password_salt=data.get("password_salt"),
                )
                session_mgr.register_restored_room(room)

                # Restore whiteboard
                wb = whiteboard_mgr.get_or_create_room_whiteboard(room_id)
                wb.load_from_state(
                    seq_num=data.get("seq_num", 0),
                    operations_data=data.get("operations", []),
                )

                # Restore chat
                chat = chat_mgr.get_or_create_room_chat(room_id)
                chat.load_history(data.get("chat_messages", []))

                restored += 1
                logger.info("Restored room '%s' from %s", room_id, p.name)
            except Exception as e:
                logger.error("Error restoring room from %s: %s", p, e)

        return restored
