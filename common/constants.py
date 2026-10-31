"""
Constants for the LAN-Based Multi-User Collaborative Whiteboard application.
Defines network, canvas, protocol, and configuration constants.
"""

# Network and Protocol Constants
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8555
DEFAULT_CLIENT_HOST = "127.0.0.1"

# TCP Framing
HEADER_SIZE = 4  # 4-byte big-endian unsigned integer prefix
MAX_MESSAGE_SIZE = 15 * 1024 * 1024  # 15 MB maximum payload to prevent memory overflow
BUFFER_SIZE = 8192  # 8 KB socket read buffer
SOCKET_TIMEOUT = 30.0  # Seconds before socket read times out for keepalive checks
PING_INTERVAL = 10.0  # Client sends heartbeat every 10 seconds
PING_TIMEOUT = 35.0  # Server disconnects client if no message/ping received in 35 seconds

# Drawing Tools
TOOL_PEN = "pen"
TOOL_ERASER = "eraser"
TOOL_LINE = "line"
TOOL_RECT = "rect"
TOOL_CIRCLE = "circle"
TOOL_TEXT = "text"
TOOL_STICKY = "sticky"
TOOL_SELECT = "select"
TOOL_LASER_PEN = "laser_pen"
TOOL_LASER_POINTER = "laser_pointer"

SUPPORTED_TOOLS = [
    TOOL_PEN,
    TOOL_ERASER,
    TOOL_LINE,
    TOOL_RECT,
    TOOL_CIRCLE,
    TOOL_TEXT,
    TOOL_STICKY,
]

# Sticky Note Color Palette
STICKY_YELLOW = "#FEF08A"
STICKY_PINK = "#FBCFE8"
STICKY_BLUE = "#BAE6FD"
STICKY_GREEN = "#BBF7D0"
STICKY_ORANGE = "#FED7AA"
STICKY_PALETTE = [
    STICKY_YELLOW,
    STICKY_PINK,
    STICKY_BLUE,
    STICKY_GREEN,
    STICKY_ORANGE,
]

# File Transfer Configurations
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB
FILE_CHUNK_SIZE = 32 * 1024  # 32 KB per base64 chunk
ALLOWED_FILE_EXTENSIONS = [
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
    ".pdf", ".txt", ".json", ".csv", ".md", ".py", ".zip",
]

# History and Replay Configurations
REPLAY_SPEEDS = [0.5, 1.0, 2.0, 4.0]

# Laser Tool Configurations
LASER_FADE_DURATION = 2.5  # seconds
LASER_COLOR = "#EF4444"  # Bright glowing red

# Canvas Configurations
DEFAULT_CANVAS_WIDTH = 2560
DEFAULT_CANVAS_HEIGHT = 1440
DEFAULT_COLOR = "#1E293B"  # Slate dark
DEFAULT_BRUSH_WIDTH = 3
DEFAULT_ERASER_WIDTH = 24
MIN_BRUSH_WIDTH = 1
MAX_BRUSH_WIDTH = 64

# Participant and Input Restrictions
MAX_USERNAME_LEN = 32
MIN_USERNAME_LEN = 1
MAX_ROOM_ID_LEN = 32
MIN_ROOM_ID_LEN = 2
MAX_PASSWORD_LEN = 64
MAX_CHAT_LEN = 1000

# Preset User Colors for distinguishing participants
USER_PALETTE = [
    "#3B82F6",  # Blue
    "#10B981",  # Emerald
    "#F59E0B",  # Amber
    "#EF4444",  # Red
    "#8B5CF6",  # Violet
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#F97316",  # Orange
    "#14B8A6",  # Teal
    "#6366F1",  # Indigo
]
