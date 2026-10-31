"""
Unit tests for Persistence Manager and State Recovery.
Tests JSON serialization, state restoration across restarts, and atomic file saves.
"""

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pytest
except ImportError:
    pytest = None

from common.constants import TOOL_PEN
from server.chat_manager import ChatManager
from server.persistence_manager import PersistenceManager
from server.session_manager import Room, SessionManager, hash_password
from server.whiteboard_manager import WhiteboardManager


def test_save_and_load_room_state():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        storage_dir = Path(tmpdir)
        pm = PersistenceManager(storage_dir)

        sm = SessionManager()
        wm = WhiteboardManager()
        cm = ChatManager()

        # 1. Create a room with password
        pwd_hash, pwd_salt = hash_password("pass123")
        room = Room(
            room_id="persisted-room",
            room_name="Persisted Architecture",
            creator_id="architect",
            password_hash=pwd_hash,
            password_salt=pwd_salt,
        )
        sm.register_restored_room(room)

        # 2. Add operations to whiteboard
        wb = wm.get_or_create_room_whiteboard("persisted-room")
        wb.add_operation(
            {"op_type": TOOL_PEN, "data": {"points": [[10, 10], [20, 20]], "color": "#000000", "width": 3}},
            "u1",
            "Alice",
        )

        # 3. Add chat message
        chat = cm.get_or_create_room_chat("persisted-room")
        chat.add_message("u1", "Alice", "Hello whiteboard team!")

        # 4. Save state
        saved = pm.save_room_state(room, wm, cm)
        assert saved

        # Verify JSON file exists
        saved_file = storage_dir / "persisted-room.json"
        assert saved_file.exists()

        # 5. Simulate Server Restart with brand new managers
        sm2 = SessionManager()
        wm2 = WhiteboardManager()
        cm2 = ChatManager()
        pm2 = PersistenceManager(storage_dir)

        restored_count = pm2.restore_all_rooms(sm2, wm2, cm2)
        assert restored_count == 1

        restored_room = sm2.get_room("persisted-room")
        assert restored_room is not None
        assert restored_room.room_name == "Persisted Architecture"
        assert restored_room.has_password

        restored_wb = wm2.get_room_whiteboard("persisted-room")
        assert restored_wb is not None
        assert restored_wb.current_seq_num == 1
        snap = restored_wb.get_snapshot()
        assert len(snap["operations"]) == 1
        assert snap["operations"][0]["username"] == "Alice"

        restored_chat = cm2.get_room_chat("persisted-room")
        assert restored_chat is not None
        history = restored_chat.get_history()
        assert len(history) == 1
        assert history[0]["text"] == "Hello whiteboard team!"
