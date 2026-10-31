"""
Message Types for LAN-Based Collaborative Whiteboard Application-Level Protocol.
Every TCP message payload contains a JSON object with a 'type' field matching one of these constants.
"""

from enum import Enum


class MessageType(str, Enum):
    # Session Management
    CREATE_ROOM = "CREATE_ROOM"
    ROOM_CREATED = "ROOM_CREATED"
    JOIN_ROOM = "JOIN_ROOM"
    JOIN_SUCCESS = "JOIN_SUCCESS"
    JOIN_FAILURE = "JOIN_FAILURE"
    LEAVE_ROOM = "LEAVE_ROOM"

    # Drawing Operations
    DRAW = "DRAW"
    ERASE = "ERASE"
    SHAPE = "SHAPE"
    CLEAR_CANVAS = "CLEAR_CANVAS"
    UNDO = "UNDO"
    REDO = "REDO"

    # Operation Acknowledgements & Modifications
    OP_ACK = "OP_ACK"
    MODIFY_OBJECT = "MODIFY_OBJECT"
    DELETE_OBJECT = "DELETE_OBJECT"
    RESTORE_STATE = "RESTORE_STATE"

    # Real-Time Laser Presentation Tools
    LASER_STROKE = "LASER_STROKE"
    LASER_POINTER = "LASER_POINTER"

    # Chunked File Transfer
    FILE_START = "FILE_START"
    FILE_CHUNK = "FILE_CHUNK"
    FILE_COMPLETE = "FILE_COMPLETE"

    # Real-Time Synchronization & Snapshots
    STATE_UPDATE = "STATE_UPDATE"
    CANVAS_SNAPSHOT = "CANVAS_SNAPSHOT"

    # Meeting Lifecycle Management
    END_MEETING = "END_MEETING"
    MEETING_ENDED = "MEETING_ENDED"

    # Text Chat
    CHAT = "CHAT"

    # Participant Notifications
    PARTICIPANT_JOINED = "PARTICIPANT_JOINED"
    PARTICIPANT_LEFT = "PARTICIPANT_LEFT"

    # Connection & Health
    PING = "PING"
    PONG = "PONG"
    ERROR = "ERROR"

    def __str__(self) -> str:
        return self.value


# Fast membership check set (accepts canonical types and tool names)
VALID_MESSAGE_TYPES = {m.value for m in MessageType} | {
    "pen",
    "eraser",
    "line",
    "rect",
    "circle",
    "text",
    "sticky",
}
