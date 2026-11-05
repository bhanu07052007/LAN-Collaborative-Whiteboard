"""
Local State Management for Collaborative Whiteboard Client.
Maintains client-side session information, tool selections, and drawing operation history.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from common.constants import (
    DEFAULT_BRUSH_WIDTH,
    DEFAULT_CLIENT_HOST,
    DEFAULT_COLOR,
    DEFAULT_ERASER_WIDTH,
    DEFAULT_PORT,
    STICKY_YELLOW,
    TOOL_PEN,
)


@dataclass
class LocalState:
    user_id: str = field(default_factory=lambda: f"user-{uuid.uuid4().hex[:8]}")
    username: str = ""
    user_color: str = "#3B82F6"
    current_room_id: Optional[str] = None
    current_room_name: Optional[str] = None
    is_host: bool = False
    server_host: str = DEFAULT_CLIENT_HOST
    server_port: int = DEFAULT_PORT
    is_connected: bool = False

    # Participants in current room: [{"user_id": ..., "username": ..., "color": ...}]
    participants: List[Dict[str, Any]] = field(default_factory=list)

    # Active tool settings
    current_tool: str = TOOL_PEN
    current_color: str = DEFAULT_COLOR
    sticky_color: str = STICKY_YELLOW
    brush_size: int = DEFAULT_BRUSH_WIDTH
    eraser_size: int = DEFAULT_ERASER_WIDTH

    # Selection state
    selected_op_id: Optional[str] = None

    # Ephemeral laser presentation state
    # [{"points": [[x, y], ...], "color": "#EF4444", "created_at": float, "fade_duration": float}]
    laser_strokes: List[Dict[str, Any]] = field(default_factory=list)
    # {sender_id: {"x": float, "y": float, "username": str, "timestamp": float}}
    laser_pointers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    laser_pointer_active: bool = False

    # Authoritative canvas operations received from server
    operations: List[Dict[str, Any]] = field(default_factory=list)
    latest_seq_num: int = 0

    # Operation Delivery Acknowledgement Tracking
    pending_ops: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    acknowledged_op_ids: Set[str] = field(default_factory=set)

    # History & Replay State
    is_in_history_mode: bool = False
    history_view_index: int = 0

    def reset_room_state(self) -> None:
        """Clears room-specific state when leaving or switching rooms."""
        self.current_room_id = None
        self.current_room_name = None
        self.is_host = False
        self.participants.clear()
        self.operations.clear()
        self.selected_op_id = None
        self.laser_strokes.clear()
        self.laser_pointers.clear()
        self.laser_pointer_active = False
        self.pending_ops.clear()
        self.acknowledged_op_ids.clear()
        self.latest_seq_num = 0
        self.is_in_history_mode = False
        self.history_view_index = 0

    def add_operation(self, op: Dict[str, Any]) -> None:
        """Appends a new drawing operation."""
        # Check if already present
        for existing in self.operations:
            if existing.get("op_id") == op.get("op_id"):
                existing.update(op)
                return
        self.operations.append(op)

    def modify_operation(self, op_id: str, new_data: Dict[str, Any]) -> bool:
        """Updates data payload of an existing operation."""
        for op in self.operations:
            if op.get("op_id") == op_id:
                if "data" not in op:
                    op["data"] = {}
                op["data"].update(new_data)
                return True
        return False

    def delete_operation(self, op_id: str) -> bool:
        """Marks an operation as deleted locally."""
        for op in self.operations:
            if op.get("op_id") == op_id:
                op["is_deleted"] = True
                return True
        return False

    def restore_deleted_operation(self, op_id: str) -> bool:
        """Restores a deleted operation back to visible active state."""
        for op in self.operations:
            if op.get("op_id") == op_id:
                op["is_deleted"] = False
                op["is_undone"] = False
                return True
        return False

    def undo_operation(self, op_id: str, op_dict: Optional[Dict[str, Any]] = None) -> bool:
        """Marks an operation as undone in the local history."""
        for op in reversed(self.operations):
            if op.get("op_id") == op_id:
                if op_dict:
                    op.update(op_dict)
                else:
                    if op.get("is_deleted", False):
                        op["is_deleted"] = False
                        op["is_undone"] = False
                    else:
                        op["is_undone"] = True
                return True
        if op_dict:
            self.operations.append(op_dict)
            return True
        return False

    def redo_operation(self, op_id: str, op_dict: Optional[Dict[str, Any]] = None) -> bool:
        """Restores an undone operation."""
        for op in reversed(self.operations):
            if op.get("op_id") == op_id:
                if op_dict:
                    op.update(op_dict)
                else:
                    op["is_undone"] = False
                return True
        if op_dict:
            self.operations.append(op_dict)
            return True
        return False

    def clear_operations(self) -> None:
        """Clears all operations locally."""
        self.operations.clear()
        self.selected_op_id = None

    def add_laser_stroke(self, user_id: str, points: List[List[float]], color: str = "#EF4444") -> None:
        """Adds a temporary laser stroke with current timestamp."""
        self.laser_strokes.append({
            "user_id": user_id,
            "points": points,
            "color": color,
            "created_at": time.time(),
        })

    def purge_expired_lasers(self, fade_duration: float = 3.0) -> bool:
        """Removes faded laser strokes older than fade_duration seconds."""
        now = time.time()
        initial_len = len(self.laser_strokes)
        self.laser_strokes = [
            s for s in self.laser_strokes
            if (now - s.get("created_at", now)) < fade_duration
        ]
        return len(self.laser_strokes) != initial_len
