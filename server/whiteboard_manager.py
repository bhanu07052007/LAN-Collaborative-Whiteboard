"""
Whiteboard Manager for LAN Collaborative Whiteboard Server.
Maintains the authoritative shared canvas state for all rooms.
Handles sequence number assignment, operation validation, user-coordinated undo/redo,
canvas clearing, and snapshot generation for late-joining clients.
"""

import copy
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from common.constants import (
    MAX_BRUSH_WIDTH,
    MIN_BRUSH_WIDTH,
    SUPPORTED_TOOLS,
    TOOL_CIRCLE,
    TOOL_ERASER,
    TOOL_LINE,
    TOOL_PEN,
    TOOL_RECT,
    TOOL_STICKY,
    TOOL_TEXT,
)

logger = logging.getLogger("WhiteboardManager")


def is_valid_hex_color(c: Any) -> bool:
    """Validates hex color strings like #RGB, #RRGGBB, or #RRGGBBAA."""
    if not isinstance(c, str):
        return False
    if not c.startswith("#"):
        return False
    hex_digits = c[1:]
    return len(hex_digits) in (3, 6, 8) and all(ch in "0123456789abcdefABCDEF" for ch in hex_digits)


@dataclass
class DrawingOperation:
    op_id: str
    op_type: str
    data: Dict[str, Any]
    user_id: str
    username: str
    seq_num: int
    created_at: float = field(default_factory=time.time)
    is_undone: bool = False
    cleared_at_seq: Optional[int] = None
    is_deleted: bool = False
    deleted_by: Optional[str] = None
    deleted_seq: Optional[int] = None
    last_undone_deleted_by: Optional[str] = None
    author_id: str = ""
    author_name: str = ""
    last_modified_by: Optional[str] = None
    last_modified_at: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.author_id:
            self.author_id = self.user_id
        if not self.author_name:
            self.author_name = self.username

    def to_dict(self) -> Dict[str, Any]:
        return {
            "op_id": self.op_id,
            "op_type": self.op_type,
            "data": copy.deepcopy(self.data),
            "user_id": self.user_id,
            "username": self.username,
            "seq_num": self.seq_num,
            "created_at": self.created_at,
            "is_undone": self.is_undone,
            "cleared_at_seq": self.cleared_at_seq,
            "is_deleted": self.is_deleted,
            "deleted_by": self.deleted_by,
            "deleted_seq": self.deleted_seq,
            "last_undone_deleted_by": self.last_undone_deleted_by,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "last_modified_by": self.last_modified_by,
            "last_modified_at": self.last_modified_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DrawingOperation":
        return cls(
            op_id=d["op_id"],
            op_type=d["op_type"],
            data=d["data"],
            user_id=d["user_id"],
            username=d["username"],
            seq_num=d["seq_num"],
            created_at=d.get("created_at", time.time()),
            is_undone=d.get("is_undone", False),
            cleared_at_seq=d.get("cleared_at_seq"),
            is_deleted=d.get("is_deleted", False),
            deleted_by=d.get("deleted_by"),
            deleted_seq=d.get("deleted_seq"),
            last_undone_deleted_by=d.get("last_undone_deleted_by"),
            author_id=d.get("author_id", d["user_id"]),
            author_name=d.get("author_name", d["username"]),
            last_modified_by=d.get("last_modified_by"),
            last_modified_at=d.get("last_modified_at"),
        )


class RoomWhiteboard:
    """Authoritative canvas state and operation log for an individual room."""

    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self._seq_num = 0
        self._operations: List[DrawingOperation] = []
        self._processed_op_ids: Dict[str, DrawingOperation] = {}
        self._lock = threading.RLock()

    @property
    def current_seq_num(self) -> int:
        with self._lock:
            return self._seq_num

    def validate_operation(self, op_dict: Dict[str, Any]) -> Tuple[bool, str]:
        """Validates drawing operation schema, coordinates, tool, color, and width."""
        if not isinstance(op_dict, dict):
            return False, "Operation must be a dictionary"

        op_type = op_dict.get("op_type")
        if op_type not in SUPPORTED_TOOLS:
            return False, f"Unsupported tool/operation type '{op_type}'"

        data = op_dict.get("data")
        if not isinstance(data, dict):
            return False, "Operation missing valid 'data' object"

        # Validate tool-specific payload
        if op_type in (TOOL_PEN, TOOL_ERASER):
            width = data.get("width")
            if width is None or not isinstance(width, (int, float)) or not (MIN_BRUSH_WIDTH <= width <= MAX_BRUSH_WIDTH):
                return False, f"Width must be between {MIN_BRUSH_WIDTH} and {MAX_BRUSH_WIDTH}"
            color = data.get("color")
            if not is_valid_hex_color(color):
                return False, f"Invalid color '{color}'"

            points = data.get("points")
            if not isinstance(points, list) or len(points) < 1:
                return False, "Pen/eraser operation must contain a non-empty list of points"
            for pt in points:
                if not (isinstance(pt, (list, tuple)) and len(pt) >= 2):
                    return False, "Points must be coordinate pairs [x, y]"
                x, y = pt[0], pt[1]
                if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
                    return False, "Point coordinates must be numeric"
                if not (-50000 <= x <= 50000 and -50000 <= y <= 50000):
                    return False, "Point coordinates out of reasonable bounds"

        elif op_type in (TOOL_LINE, TOOL_RECT, TOOL_CIRCLE):
            width = data.get("width")
            if width is None or not isinstance(width, (int, float)) or not (MIN_BRUSH_WIDTH <= width <= MAX_BRUSH_WIDTH):
                return False, f"Width must be between {MIN_BRUSH_WIDTH} and {MAX_BRUSH_WIDTH}"
            color = data.get("color")
            if not is_valid_hex_color(color):
                return False, f"Invalid color '{color}'"

            start = data.get("start")
            end = data.get("end")
            if not (isinstance(start, (list, tuple)) and len(start) >= 2):
                return False, "Shape must contain valid 'start' [x, y]"
            if not (isinstance(end, (list, tuple)) and len(end) >= 2):
                return False, "Shape must contain valid 'end' [x, y]"
            for coord in (start[0], start[1], end[0], end[1]):
                if not isinstance(coord, (int, float)) or not (-50000 <= coord <= 50000):
                    return False, "Coordinates out of bounds"

        elif op_type == TOOL_TEXT:
            x = data.get("x")
            y = data.get("y")
            if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
                return False, "Text coordinates must be numeric [x, y]"
            text = data.get("text", "")
            if not isinstance(text, str):
                return False, "Text content must be a string"
            color = data.get("color", "#000000")
            if not is_valid_hex_color(color):
                return False, f"Invalid text color '{color}'"

        elif op_type == TOOL_STICKY:
            x = data.get("x")
            y = data.get("y")
            w = data.get("width", 180)
            h = data.get("height", 140)
            if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
                return False, "Sticky note coordinates must be numeric [x, y]"
            if not (isinstance(w, (int, float)) and isinstance(h, (int, float)) and w >= 20 and h >= 20):
                return False, "Sticky note dimensions must be positive numbers >= 20"
            color = data.get("color", "#FEF08A")
            if not is_valid_hex_color(color):
                return False, f"Invalid sticky note color '{color}'"

        return True, ""

    def add_operation(
        self,
        op_dict: Dict[str, Any],
        user_id: str,
        username: str,
    ) -> Tuple[bool, str, Optional[DrawingOperation]]:
        """
        Validates, sequences, and records a drawing operation.
        Applies deduplication for repeated op_ids.
        Thread-safe under room lock.
        """
        op_id = op_dict.get("op_id") or str(uuid.uuid4())

        with self._lock:
            # Check for deduplication
            if op_id in self._processed_op_ids:
                existing_op = self._processed_op_ids[op_id]
                logger.info("Room %s: Deduplicated existing op %s (seq %d)", self.room_id, op_id, existing_op.seq_num)
                return True, "Duplicate operation acknowledged", existing_op

            is_valid, reason = self.validate_operation(op_dict)
            if not is_valid:
                return False, reason, None

            self._seq_num += 1
            op = DrawingOperation(
                op_id=op_id,
                op_type=op_dict["op_type"],
                data=op_dict["data"],
                user_id=user_id,
                username=username,
                seq_num=self._seq_num,
                author_id=user_id,
                author_name=username,
            )
            self._operations.append(op)
            self._processed_op_ids[op_id] = op
            logger.debug("Room %s: assigned seq %d to %s op %s", self.room_id, self._seq_num, op.op_type, op.op_id)
            return True, "", op

    def modify_operation(
        self,
        op_id: str,
        new_data: Dict[str, Any],
        modifier_id: str,
        modifier_name: str,
    ) -> Tuple[bool, str, Optional[DrawingOperation]]:
        """
        Modifies properties of an existing object (e.g. moved coordinates, resized dimensions, edited text).
        Preserves original author attribution!
        """
        with self._lock:
            for op in self._operations:
                if op.op_id == op_id and not op.is_deleted:
                    self._seq_num += 1
                    op.data.update(new_data)
                    op.last_modified_by = modifier_name
                    op.last_modified_at = time.time()
                    logger.info("Room %s: Op %s modified by %s (author preserved as %s)",
                                self.room_id, op_id, modifier_name, op.author_name)
                    return True, "Object modified", op

            return False, f"Object '{op_id}' not found or already deleted", None

    def delete_operation(self, op_id: str, user_id: str) -> Tuple[bool, str, Optional[DrawingOperation]]:
        """
        Marks an object as deleted by user_id.
        """
        with self._lock:
            for op in self._operations:
                if op.op_id == op_id and not op.is_deleted:
                    self._seq_num += 1
                    op.is_deleted = True
                    op.deleted_by = user_id
                    op.deleted_seq = self._seq_num
                    op.last_undone_deleted_by = None
                    logger.info("Room %s: Op %s deleted by %s (seq %d)", self.room_id, op_id, user_id, self._seq_num)
                    return True, "Object deleted", op

            return False, f"Object '{op_id}' not found or already deleted", None

    def restore_to_seq(self, target_seq: int) -> Tuple[bool, str, List[DrawingOperation]]:
        """
        Restores state of the whiteboard to target_seq.
        Operations sequenced after target_seq are marked undone.
        """
        with self._lock:
            if target_seq < 0 or (self._operations and target_seq > self._seq_num):
                return False, "Target sequence out of range", []

            self._seq_num += 1
            for op in self._operations:
                if op.seq_num > target_seq:
                    op.is_undone = True
                else:
                    if op.cleared_at_seq is not None and op.cleared_at_seq > target_seq:
                        op.cleared_at_seq = None
                    op.is_undone = False

            active_ops = [op for op in self._operations if not op.is_undone and op.cleared_at_seq is None and not op.is_deleted]
            logger.info("Room %s: Whiteboard restored to seq %d (%d active ops)", self.room_id, target_seq, len(active_ops))
            return True, f"Restored to sequence {target_seq}", active_ops

    def undo_last_user_operation(self, user_id: str) -> Tuple[bool, str, Optional[DrawingOperation]]:
        """
        Undoes the most recent active operation or deletion performed by user_id.
        Restores deleted objects if the last action by user was a deletion.
        Returns (success, message, affected_operation).
        """
        with self._lock:
            cand_del = None
            cand_draw = None

            for op in reversed(self._operations):
                if op.cleared_at_seq is not None:
                    continue
                if cand_del is None and op.is_deleted and op.deleted_by == user_id:
                    cand_del = op
                if cand_draw is None and not op.is_deleted and not op.is_undone and op.user_id == user_id:
                    cand_draw = op

            del_seq = (cand_del.deleted_seq or 0) if cand_del else -1
            draw_seq = cand_draw.seq_num if cand_draw else -1

            if cand_del and del_seq >= draw_seq:
                self._seq_num += 1
                cand_del.is_deleted = False
                cand_del.is_undone = False
                cand_del.deleted_by = None
                cand_del.deleted_seq = None
                cand_del.last_undone_deleted_by = user_id
                logger.info("Room %s: User %s undid deletion of op %s (restored at seq %d)",
                            self.room_id, user_id, cand_del.op_id, self._seq_num)
                return True, "Deletion undone, object restored", cand_del

            elif cand_draw:
                self._seq_num += 1
                cand_draw.is_undone = True
                logger.info("Room %s: User %s undid op %s (seq %d)",
                            self.room_id, user_id, cand_draw.op_id, self._seq_num)
                return True, "Operation undone", cand_draw

            return False, "No active operations to undo for this user", None

    def redo_last_user_operation(self, user_id: str) -> Tuple[bool, str, Optional[DrawingOperation]]:
        """
        Redoes the most recent undone operation or undone deletion performed by user_id.
        Returns (success, message, affected_operation).
        """
        with self._lock:
            cand_del = None
            cand_draw = None

            for op in reversed(self._operations):
                if op.cleared_at_seq is not None:
                    continue
                if cand_del is None and not op.is_deleted and op.last_undone_deleted_by == user_id:
                    cand_del = op
                if cand_draw is None and not op.is_deleted and op.is_undone and op.user_id == user_id:
                    cand_draw = op

            if cand_del:
                self._seq_num += 1
                cand_del.is_deleted = True
                cand_del.deleted_by = user_id
                cand_del.deleted_seq = self._seq_num
                cand_del.last_undone_deleted_by = None
                logger.info("Room %s: User %s redid deletion of op %s (seq %d)",
                            self.room_id, user_id, cand_del.op_id, self._seq_num)
                return True, "Operation restored (deleted)", cand_del

            elif cand_draw:
                self._seq_num += 1
                cand_draw.is_undone = False
                logger.info("Room %s: User %s redid op %s (seq %d)",
                            self.room_id, user_id, cand_draw.op_id, self._seq_num)
                return True, "Operation restored", cand_draw

            return False, "No undone operations to redo for this user", None

    def clear_canvas(self, user_id: str, username: str) -> Tuple[int, int]:
        """
        Marks all active operations as cleared at the current sequence number.
        Returns (new_seq_num, cleared_count).
        """
        with self._lock:
            self._seq_num += 1
            clear_seq = self._seq_num
            cleared_count = 0
            for op in self._operations:
                if not op.is_undone and op.cleared_at_seq is None:
                    op.cleared_at_seq = clear_seq
                    cleared_count += 1

            logger.info("Room %s: Canvas cleared by %s (%s), %d ops cleared at seq %d",
                        self.room_id, username, user_id, cleared_count, clear_seq)
            return clear_seq, cleared_count

    def get_snapshot(self) -> Dict[str, Any]:
        """
        Generates an authoritative snapshot containing:
        - Current sequence number
        - All visible active operations in sequential order
        """
        with self._lock:
            active_ops = [
                op.to_dict()
                for op in self._operations
                if not op.is_undone and op.cleared_at_seq is None and not op.is_deleted
            ]
            return {
                "room_id": self.room_id,
                "seq_num": self._seq_num,
                "operations": active_ops,
            }

    def get_full_history(self) -> List[Dict[str, Any]]:
        """Returns all operations including undone/cleared for persistence."""
        with self._lock:
            return [op.to_dict() for op in self._operations]

    def load_from_state(self, seq_num: int, operations_data: List[Dict[str, Any]]) -> None:
        """Restores state from persisted operations."""
        with self._lock:
            self._seq_num = seq_num
            self._operations = [DrawingOperation.from_dict(d) for d in operations_data]
            self._processed_op_ids = {op.op_id: op for op in self._operations}
            logger.info("Room %s restored %d operations, seq %d", self.room_id, len(self._operations), self._seq_num)


class WhiteboardManager:
    """Manages whiteboard states across all active rooms."""

    def __init__(self) -> None:
        self._rooms: Dict[str, RoomWhiteboard] = {}
        self._lock = threading.RLock()

    def get_or_create_room_whiteboard(self, room_id: str) -> RoomWhiteboard:
        with self._lock:
            if room_id not in self._rooms:
                self._rooms[room_id] = RoomWhiteboard(room_id)
            return self._rooms[room_id]

    def get_room_whiteboard(self, room_id: str) -> Optional[RoomWhiteboard]:
        with self._lock:
            return self._rooms.get(room_id)

    def delete_room_whiteboard(self, room_id: str) -> None:
        with self._lock:
            self._rooms.pop(room_id, None)
