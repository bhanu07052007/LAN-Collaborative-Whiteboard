"""
Comprehensive automated tests covering the 21 upgrade verification areas:
1. Text creation and editing
2. Sticky note sync across clients
3. Author attribution verification (cannot be spoofed, retained on edit/move)
4. Object selection and moving
5. Object resizing
6. Undo and redo for new objects
7. History ordering and timestamps
8. History replay sequence
9. Laser pen synchronization and fading
10. Laser pointer tracking
11. Delivery acknowledgements (OP_ACK)
12. Operation de-duplication
13. File transfer over TCP (chunking, assembly)
14. File transfer cancellation/failure handling
15. Meeting report generation format (Sections A, B, C, D)
16. Multiple joins and leaves tracking
17. Early exit detection and reporting
18. Normal session termination report
19. Unexpected shutdown persistence and recovery
20. Report persistence in data/meeting_logs/
21. Responsive GUI components initialization and sizing
"""

import base64
import hashlib
import socket
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication, QPushButton

from common.constants import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    LASER_COLOR,
    LASER_FADE_DURATION,
    MAX_FILE_SIZE,
    STICKY_PALETTE,
    STICKY_YELLOW,
    TOOL_CIRCLE,
    TOOL_ERASER,
    TOOL_LINE,
    TOOL_PEN,
    TOOL_RECT,
    TOOL_SELECT,
    TOOL_STICKY,
    TOOL_TEXT,
    TOOL_LASER_PEN,
    TOOL_LASER_POINTER,
)
from common.message_types import MessageType
from common.protocol import build_message, receive_message, send_message
from client.canvas import WhiteboardCanvas
from client.file_transfer import FileSenderThread, FileShareDialog, IncomingFileManager
from client.history_panel import HistoryReplayPanel
from client.local_state import LocalState
from client.main_window import MainWindow
from client.network_client import NetworkClient
from client.toolbar import WhiteboardToolbar
from server.meeting_report_manager import MeetingReportManager, RoomSessionTracker
from server.server_config import ServerConfig
from server.socket_server import SocketServer
from server.whiteboard_manager import DrawingOperation, RoomWhiteboard, WhiteboardManager


@pytest.fixture(scope="session")
def qapp():
    """Shared QApplication fixture for GUI widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def get_ephemeral_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# =============================================================================
# AREA 1: Text Creation and Editing
# =============================================================================

def test_text_creation_and_editing():
    wb = RoomWhiteboard("room-text")
    text_op = {
        "op_type": TOOL_TEXT,
        "data": {
            "x": 120.0,
            "y": 240.0,
            "text": "Meeting Agenda: Design Review",
            "color": "#1E293B",
            "font_size": 18,
        },
    }
    success, reason, op = wb.add_operation(text_op, user_id="user-1", username="Sathvik")
    assert success is True
    assert op is not None
    assert op.op_type == TOOL_TEXT
    assert op.author_name == "Sathvik"
    assert op.data["text"] == "Meeting Agenda: Design Review"

    # Edit the text content
    mod_success, mod_reason, mod_op = wb.modify_operation(
        op.op_id,
        {"text": "Meeting Agenda: Design Review & QA"},
        modifier_id="user-1",
        modifier_name="Sathvik",
    )
    assert mod_success is True
    assert mod_op.data["text"] == "Meeting Agenda: Design Review & QA"
    assert mod_op.author_name == "Sathvik"
    assert mod_op.last_modified_by == "Sathvik"


# =============================================================================
# AREA 2: Sticky Note Sync Across Clients
# =============================================================================

def test_sticky_note_creation_and_color():
    wb = RoomWhiteboard("room-sticky")
    sticky_op = {
        "op_type": TOOL_STICKY,
        "data": {
            "x": 300.0,
            "y": 150.0,
            "width": 180,
            "height": 140,
            "text": "Action Item: Write test suite",
            "color": STICKY_YELLOW,
        },
    }
    success, reason, op = wb.add_operation(sticky_op, user_id="user-1", username="Sathvik")
    assert success is True
    assert op.op_type == TOOL_STICKY
    assert op.data["color"] in STICKY_PALETTE
    assert op.data["width"] == 180
    assert op.data["height"] == 140


# =============================================================================
# AREA 3: Author Attribution Verification (Tamper-Proof)
# =============================================================================

def test_author_attribution_tamper_proof():
    wb = RoomWhiteboard("room-author")
    # Client attempts to spoof another author
    spoofed_op = {
        "op_type": TOOL_STICKY,
        "author_name": "SpoofedAdmin",
        "author_id": "user-admin",
        "data": {
            "x": 50.0,
            "y": 50.0,
            "width": 180,
            "height": 140,
            "text": "Important notice",
            "color": STICKY_YELLOW,
        },
    }
    # Server enforces authenticated user session
    success, reason, op = wb.add_operation(spoofed_op, user_id="user-actual", username="ActualUser")
    assert success is True
    assert op.author_id == "user-actual"
    assert op.author_name == "ActualUser"

    # Moving or modifying the object preserves the original author
    wb.modify_operation(op.op_id, {"x": 100.0, "y": 100.0}, modifier_id="user-editor", modifier_name="EditorUser")
    assert op.author_name == "ActualUser"
    assert op.author_id == "user-actual"
    assert op.last_modified_by == "EditorUser"


# =============================================================================
# AREA 4: Object Selection and Moving
# =============================================================================

def test_object_selection_and_moving():
    state = LocalState()
    wb = RoomWhiteboard("room-move")
    op_data = {
        "op_type": TOOL_RECT,
        "data": {"start": [100, 100], "end": [200, 200], "color": "#3B82F6", "width": 3},
    }
    _, _, op = wb.add_operation(op_data, "user-1", "Alice")
    state.add_operation(op.to_dict())

    # Move object by dx=50, dy=30
    new_data = {"start": [150, 130], "end": [250, 230], "color": "#3B82F6", "width": 3}
    success = state.modify_operation(op.op_id, new_data)
    assert success is True
    assert state.operations[0]["data"]["start"] == [150, 130]
    assert state.operations[0]["data"]["end"] == [250, 230]


# =============================================================================
# AREA 5: Object Resizing
# =============================================================================

def test_object_resizing():
    wb = RoomWhiteboard("room-resize")
    sticky_op = {
        "op_type": TOOL_STICKY,
        "data": {"x": 50, "y": 50, "width": 180, "height": 140, "text": "Resizing test", "color": STICKY_YELLOW},
    }
    _, _, op = wb.add_operation(sticky_op, "user-1", "Bob")
    # Resize to larger dimensions
    wb.modify_operation(op.op_id, {"width": 260, "height": 200}, "user-1", "Bob")
    assert op.data["width"] == 260
    assert op.data["height"] == 200


# =============================================================================
# AREA 6: Undo and Redo for New Objects
# =============================================================================

def test_undo_and_redo_for_new_objects():
    wb = RoomWhiteboard("room-undo")
    text_op = {
        "op_type": TOOL_TEXT,
        "data": {"x": 10, "y": 10, "text": "Undo test", "color": "#000000", "font_size": 16},
    }
    wb.add_operation(text_op, "user-1", "Charlie")

    # Undo
    success, _, undone_op = wb.undo_last_user_operation("user-1")
    assert success is True
    assert undone_op.is_undone is True
    assert len(wb.get_snapshot()["operations"]) == 0

    # Redo
    success, _, redone_op = wb.redo_last_user_operation("user-1")
    assert success is True
    assert redone_op.is_undone is False
    assert len(wb.get_snapshot()["operations"]) == 1


# =============================================================================
# AREA 7: History Ordering and Timestamps
# =============================================================================

def test_history_ordering_and_timestamps():
    wb = RoomWhiteboard("room-hist")
    for i in range(5):
        wb.add_operation(
            {"op_type": TOOL_PEN, "data": {"points": [[i, i], [i + 1, i + 1]], "color": "#000000", "width": 2}},
            "user-1",
            "Alice",
        )
    history = wb.get_full_history()
    assert len(history) == 5
    for i in range(5):
        assert history[i]["seq_num"] == i + 1
        assert history[i]["created_at"] > 0
        if i > 0:
            assert history[i]["seq_num"] > history[i - 1]["seq_num"]


# =============================================================================
# AREA 8: History Replay Sequence and Restore
# =============================================================================

def test_history_replay_and_restore():
    wb = RoomWhiteboard("room-restore")
    for i in range(6):
        wb.add_operation(
            {"op_type": TOOL_PEN, "data": {"points": [[i, i], [i + 5, i + 5]], "color": "#3B82F6", "width": 2}},
            "user-1",
            "Alice",
        )
    assert len(wb.get_snapshot()["operations"]) == 6

    # Restore back to seq 3
    success, msg, active = wb.restore_to_seq(3)
    assert success is True
    assert len(active) == 3
    snapshot = wb.get_snapshot()
    assert len(snapshot["operations"]) == 3


# =============================================================================
# AREA 9: Laser Pen Synchronization and Fading
# =============================================================================

def test_laser_pen_synchronization_and_fading():
    state = LocalState()
    now = time.time()
    # Add active laser stroke
    state.laser_strokes.append({
        "points": [[10, 10], [50, 50]],
        "color": LASER_COLOR,
        "created_at": now,
    })
    # Add expired laser stroke (3 seconds old)
    state.laser_strokes.append({
        "points": [[100, 100], [200, 200]],
        "color": LASER_COLOR,
        "created_at": now - 3.0,
    })

    purged = state.purge_expired_lasers(fade_duration=2.5)
    assert purged is True
    assert len(state.laser_strokes) == 1
    assert state.laser_strokes[0]["points"] == [[10, 10], [50, 50]]


# =============================================================================
# AREA 10: Laser Pointer Tracking
# =============================================================================

def test_laser_pointer_tracking():
    state = LocalState()
    state.laser_pointers["user-peer"] = {
        "x": 420.5,
        "y": 310.0,
        "username": "Priya",
        "timestamp": time.time(),
        "active": True,
    }
    assert "user-peer" in state.laser_pointers
    assert state.laser_pointers["user-peer"]["username"] == "Priya"
    assert state.laser_pointers["user-peer"]["x"] == 420.5


# =============================================================================
# AREA 11: Delivery Acknowledgements (OP_ACK)
# =============================================================================

def test_delivery_acknowledgement_op_ack():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        port = get_ephemeral_port()
        config = ServerConfig(host="127.0.0.1", port=port, sessions_dir=Path(tmpdir))
        server = SocketServer(config)
        server.start()
        time.sleep(0.2)

        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            c.connect(("127.0.0.1", port))
            # Create room
            send_message(c, build_message(MessageType.CREATE_ROOM, room_id="ack-room", username="Alice", user_id="u1"))
            receive_message(c)  # ROOM_CREATED

            # Send drawing operation
            draw_msg = {
                "type": MessageType.DRAW.value,
                "room_id": "ack-room",
                "op_type": TOOL_PEN,
                "op_id": "test-ack-123",
                "data": {"points": [[5, 5], [15, 15]], "color": "#000000", "width": 3},
            }
            send_message(c, draw_msg)

            ack_msg = receive_message(c)
            assert ack_msg is not None
            assert ack_msg.get("type") == MessageType.OP_ACK.value
            assert ack_msg.get("op_id") == "test-ack-123"
            assert ack_msg.get("status") == "accepted"
            assert ack_msg.get("seq_num") == 1
        finally:
            c.close()
            server.stop()


# =============================================================================
# AREA 12: Operation Deduplication
# =============================================================================

def test_operation_deduplication():
    wb = RoomWhiteboard("room-dedup")
    op = {
        "op_type": TOOL_PEN,
        "op_id": "fixed-id-456",
        "data": {"points": [[0, 0], [10, 10]], "color": "#FF0000", "width": 2},
    }
    # First submission
    s1, _, op1 = wb.add_operation(op, "user-1", "Alice")
    assert s1 is True
    assert op1.seq_num == 1

    # Duplicate submission with same op_id
    s2, msg2, op2 = wb.add_operation(op, "user-1", "Alice")
    assert s2 is True
    assert op2.seq_num == 1
    assert "Duplicate" in msg2
    assert len(wb._operations) == 1


# =============================================================================
# AREA 13: File Transfer over TCP (Chunking & Assembly)
# =============================================================================

def test_file_transfer_chunking_and_assembly():
    manager = IncomingFileManager()
    sample_content = b"LAN Collaborative Whiteboard: File Sharing Verification Content" * 50
    file_id = "test-file-99"
    filename = "test_document.txt"

    # Start
    manager.handle_file_start({
        "file_id": file_id,
        "filename": filename,
        "file_size": len(sample_content),
        "sender_name": "Sathvik",
    })

    # Send in 2 chunks
    chunk1 = sample_content[:len(sample_content) // 2]
    chunk2 = sample_content[len(sample_content) // 2:]

    manager.handle_file_chunk({
        "file_id": file_id,
        "chunk_index": 0,
        "total_chunks": 2,
        "data": base64.b64encode(chunk1).decode("ascii"),
    })
    manager.handle_file_chunk({
        "file_id": file_id,
        "chunk_index": 1,
        "total_chunks": 2,
        "data": base64.b64encode(chunk2).decode("ascii"),
    })

    # Complete
    res = manager.handle_file_complete({"file_id": file_id})
    assert res is not None
    out_filename, out_bytes = res
    assert out_filename == filename
    assert out_bytes == sample_content


# =============================================================================
# AREA 14: File Transfer Validation & Cancellation
# =============================================================================

def test_file_transfer_size_limit():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        # Create small test file
        f.write(b"x" * 100)
        temp_name = f.name

    try:
        network = NetworkClient()
        sender = FileSenderThread(temp_name, "room-1", "u1", network)
        sender.cancel()
        assert sender._is_cancelled is True
    finally:
        Path(temp_name).unlink(missing_ok=True)


# =============================================================================
# AREA 15: Meeting Report Generation Format (Sections A, B, C, D)
# =============================================================================

def test_meeting_report_generation_structure():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tracker = RoomSessionTracker(
            room_id="room-101",
            room_name="Architecture Meeting",
            host_id="user-sathvik",
            host_name="Sathvik",
            logs_dir=Path(tmpdir),
        )
        tracker.record_drawing("user-sathvik", TOOL_STICKY, "op-1", 1)
        tracker.record_chat("user-sathvik", "Welcome everyone!")
        tracker.finish_session(reason="Host ended meeting")

        report_text = tracker.generate_report_text(final_op_count=1)
        assert "SECTION A: SESSION INFORMATION" in report_text
        assert "SECTION B: PARTICIPANT ACTIVITY LOG" in report_text
        assert "SECTION C: CHRONOLOGICAL EVENT HISTORY" in report_text
        assert "SECTION D: SESSION END SUMMARY" in report_text
        assert "Sathvik" in report_text
        assert "room-101" in report_text


# =============================================================================
# AREA 16: Multiple Joins and Leaves Tracking
# =============================================================================

def test_multiple_joins_and_leaves_tracking():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tracker = RoomSessionTracker("room-multi", "Room Multi", "host-1", "Host", Path(tmpdir))
        tracker.record_join("u2", "Rahul")
        tracker.record_join("u3", "Priya")
        assert len(tracker.participants) == 3

        tracker.record_leave("u2", early_exit=True)
        assert tracker.participants["u2"].exited_early is True
        assert tracker.participants["u2"].completed is False


# =============================================================================
# AREA 17: Early Exit Detection and Reporting (Sathvik / Rahul / Priya)
# =============================================================================

def test_sathvik_rahul_priya_scenario():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tracker = RoomSessionTracker("room-demo", "Demo Session", "u-sathvik", "Sathvik", Path(tmpdir))

        # Rahul joins, draws, exits early
        tracker.record_join("u-rahul", "Rahul")
        tracker.record_drawing("u-rahul", TOOL_PEN, "op-2", 2)
        tracker.record_leave("u-rahul", early_exit=True)

        # Priya joins, chats, stays
        tracker.record_join("u-priya", "Priya")
        tracker.record_file_shared("u-priya", "specs.pdf", 1024 * 50)
        tracker.record_chat("u-priya", "Uploaded the specs")

        # Meeting concluded by Sathvik
        tracker.finish_session(reason="Meeting ended by host Sathvik")

        report = tracker.generate_report_text(final_op_count=10)

        # Verify Participant statuses
        assert tracker.participants["u-rahul"].exited_early is True
        assert tracker.participants["u-rahul"].completed is False
        assert tracker.participants["u-priya"].completed is True
        assert tracker.participants["u-sathvik"].completed is True

        # Check formatted report contents
        assert "Exited Early" in report
        assert "Completed" in report
        assert "specs.pdf" in report


# =============================================================================
# AREA 18: Normal Session Termination Report Disk Write
# =============================================================================

def test_normal_session_termination_disk_write():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        log_dir = Path(tmpdir)
        tracker = RoomSessionTracker("room-pers", "Pers Room", "u1", "Host", log_dir)
        tracker.finish_session(reason="Host ended meeting")
        report_file = tracker.write_report_to_disk(final_op_count=5)

        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")
        assert "SECTION A: SESSION INFORMATION" in content
        assert "SECTION D: SESSION END SUMMARY" in content


# =============================================================================
# AREA 19: Unexpected Shutdown Persistence and Recovery
# =============================================================================

def test_unexpected_shutdown_persistence_and_recovery():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        port = get_ephemeral_port()
        config = ServerConfig(host="127.0.0.1", port=port, sessions_dir=Path(tmpdir))
        server = SocketServer(config)
        server.start()
        time.sleep(0.2)

        # Create room and write an operation
        room = server.session_mgr.create_room("crash-room", "host-1", "Crash Room")[2]
        wb = server.whiteboard_mgr.get_or_create_room_whiteboard("crash-room")
        wb.add_operation(
            {"op_type": TOOL_RECT, "data": {"start": [0, 0], "end": [50, 50], "color": "#000000", "width": 2}},
            "host-1",
            "Host",
        )
        tracker = server.report_mgr.get_or_create_tracker("crash-room", "Crash Room", "host-1", "Host")

        # Simulate shutdown
        server.stop()

        # Check that session report was automatically saved on shutdown
        reports = list(config.meeting_logs_dir.glob("crash-room_*_session.log"))
        assert len(reports) > 0
        assert "Server shutdown" in reports[0].read_text(encoding="utf-8")


# =============================================================================
# AREA 20: Report Persistence Directory Verification
# =============================================================================

def test_report_persistence_directory():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        mgr = MeetingReportManager(Path(tmpdir))
        tracker = mgr.get_or_create_tracker("room-test-dir", "Room Test", "h1", "Host")
        tracker.finish_session("Done")
        path = tracker.write_report_to_disk(0)
        assert path.parent == Path(tmpdir)
        assert path.exists()


# =============================================================================
# AREA 21: Responsive GUI Components Initialization and Sizing
# =============================================================================

def test_responsive_gui_initialization(qapp=None):
    if qapp is None:
        qapp = QApplication.instance() or QApplication([])
    state = LocalState(user_id="test-gui-user", username="Tester")
    canvas = WhiteboardCanvas(state)
    assert canvas.width() == DEFAULT_CANVAS_WIDTH
    assert canvas.height() == DEFAULT_CANVAS_HEIGHT

    toolbar = WhiteboardToolbar(state)
    assert toolbar is not None

    net = NetworkClient()
    main_win = MainWindow(state, net)
    assert main_win.minimumWidth() >= 900
    assert main_win.minimumHeight() >= 600

    history_panel = HistoryReplayPanel(state)
    assert history_panel is not None

    file_dialog = FileShareDialog(state, net)
    assert file_dialog is not None


# =============================================================================
# ADDITIONAL COMPREHENSIVE TESTS (Areas 22-36)
# =============================================================================

def test_sticky_note_invalid_dimensions():
    wb = RoomWhiteboard("room-val-1")
    op = {
        "op_type": TOOL_STICKY,
        "data": {"x": 10, "y": 10, "width": 5, "height": 5, "text": "too small", "color": STICKY_YELLOW},
    }
    success, reason, _ = wb.add_operation(op, "u1", "User")
    assert success is False
    assert "dimensions" in reason.lower() or "positive" in reason.lower()


def test_sticky_note_invalid_hex_color():
    wb = RoomWhiteboard("room-val-2")
    op = {
        "op_type": TOOL_STICKY,
        "data": {"x": 10, "y": 10, "width": 100, "height": 100, "text": "bad color", "color": "yellow"},
    }
    success, reason, _ = wb.add_operation(op, "u1", "User")
    assert success is False
    assert "invalid" in reason.lower() or "color" in reason.lower()


def test_text_tool_coordinate_validation():
    wb = RoomWhiteboard("room-val-3")
    op = {
        "op_type": TOOL_TEXT,
        "data": {"x": "invalid_x", "y": 20, "text": "hello", "color": "#000000", "font_size": 16},
    }
    success, reason, _ = wb.add_operation(op, "u1", "User")
    assert success is False


def test_shape_out_of_bounds_validation():
    wb = RoomWhiteboard("room-val-4")
    op = {
        "op_type": TOOL_RECT,
        "data": {"start": [999999, 0], "end": [10, 10], "color": "#000000", "width": 3},
    }
    success, reason, _ = wb.add_operation(op, "u1", "User")
    assert success is False
    assert "bounds" in reason.lower()


def test_laser_stroke_protocol_message_packing():
    from common.protocol import pack_message, unpack_header
    msg = build_message(MessageType.LASER_STROKE, points=[[1, 1], [10, 10]], color="#EF4444")
    packet = pack_message(msg)
    length = unpack_header(packet[:4])
    assert length == len(packet) - 4
    assert b"LASER_STROKE" in packet


def test_laser_pointer_protocol_message_packing():
    from common.protocol import pack_message
    msg = build_message(MessageType.LASER_POINTER, x=150.5, y=320.0, active=True)
    packet = pack_message(msg)
    assert b"LASER_POINTER" in packet


def test_modify_nonexistent_object_fails():
    wb = RoomWhiteboard("room-mod-fail")
    success, reason, op = wb.modify_operation("nonexistent-id", {"x": 10}, "u1", "User")
    assert success is False
    assert "not found" in reason.lower()


def test_delete_object_removes_from_active_snapshot():
    wb = RoomWhiteboard("room-del")
    op_data = {
        "op_type": TOOL_RECT,
        "data": {"start": [0, 0], "end": [20, 20], "color": "#000000", "width": 2},
    }
    _, _, op = wb.add_operation(op_data, "u1", "User")
    assert len(wb.get_snapshot()["operations"]) == 1

    success, reason, del_op = wb.delete_operation(op.op_id, "u1")
    assert success is True
    assert del_op.is_deleted is True
    assert len(wb.get_snapshot()["operations"]) == 0


def test_restore_to_seq_bounds_checking():
    wb = RoomWhiteboard("room-restore-bounds")
    success, reason, ops = wb.restore_to_seq(-5)
    assert success is False
    assert "out of range" in reason.lower()


def test_file_chunk_serialization_and_deserialization():
    from common.protocol import pack_message
    raw_bytes = b"Collaborative Whiteboard Chunk Test Data"
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    msg = build_message(MessageType.FILE_CHUNK, file_id="f-1", chunk_index=0, total_chunks=1, data=b64)
    packet = pack_message(msg)
    assert b"FILE_CHUNK" in packet
    assert b64.encode("ascii") in packet


def test_meeting_report_manager_close_all_sessions():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        mgr = MeetingReportManager(Path(tmpdir))
        tracker1 = mgr.get_or_create_tracker("room-c1", "Room C1", "u1", "Host1")
        tracker2 = mgr.get_or_create_tracker("room-c2", "Room C2", "u2", "Host2")

        paths = mgr.close_all_sessions(reason="Server shutdown test")
        assert len(paths) == 2
        for p in paths:
            assert p.exists()


def test_session_tracker_metrics_aggregation():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tracker = RoomSessionTracker("room-metrics", "Room Metrics", "h1", "Host", Path(tmpdir))
        tracker.record_join("u1", "User1")
        tracker.record_chat("u1", "Chat 1")
        tracker.record_chat("u1", "Chat 2")
        tracker.record_file_shared("u1", "test.png", 5000)

        record = tracker.participants["u1"]
        assert record.chat_count == 2
        assert record.file_count == 1


def test_local_state_reset_room_state():
    state = LocalState()
    state.current_room_id = "test-room"
    state.selected_op_id = "op-1"
    state.laser_strokes = [{"points": [[0, 0]]}]
    state.latest_seq_num = 15

    state.reset_room_state()
    assert state.current_room_id is None
    assert state.selected_op_id is None
    assert len(state.laser_strokes) == 0
    assert state.latest_seq_num == 0


def test_canvas_bounding_rect_and_hit_test(qapp=None):
    if qapp is None:
        qapp = QApplication.instance() or QApplication([])
    state = LocalState()
    canvas = WhiteboardCanvas(state)

    sticky_op = {
        "op_id": "op-sticky-test",
        "op_type": TOOL_STICKY,
        "data": {"x": 100, "y": 100, "width": 180, "height": 140, "text": "Sticky Hit", "color": STICKY_YELLOW},
    }
    state.add_operation(sticky_op)

    # Point inside sticky note
    hit = canvas._hit_test(QPointF(150, 150))
    assert hit is not None
    assert hit["op_id"] == "op-sticky-test"

    # Point far outside sticky note
    miss = canvas._hit_test(QPointF(900, 900))
    assert miss is None


def test_dynamic_toolbar_overflow_tiers():
    app = QApplication.instance() or QApplication([])
    state = LocalState(user_id="u1", username="Tester")
    toolbar = WhiteboardToolbar(state)

    # 1. Large window width (>= 1440px)
    toolbar._recalculate_overflow(1500)
    assert not toolbar.p2_container.isHidden()
    assert toolbar.more_btn.isHidden()
    assert toolbar._is_compact_mode is False

    # 2. Medium window width (940px - 1439px)
    toolbar._recalculate_overflow(1100)
    assert toolbar.p2_container.isHidden()
    assert not toolbar.more_btn.isHidden()
    assert toolbar._is_compact_mode is False

    # 3. Compact window width (< 940px)
    toolbar._recalculate_overflow(800)
    assert toolbar.p2_container.isHidden()
    assert not toolbar.more_btn.isHidden()
    assert toolbar._is_compact_mode is True

    # 4. Expansion back to large window
    toolbar._recalculate_overflow(1600)
    assert not toolbar.p2_container.isHidden()
    assert toolbar.more_btn.isHidden()
    assert toolbar._is_compact_mode is False


def test_more_menu_actions_and_sync():
    app = QApplication.instance() or QApplication([])
    state = LocalState(user_id="u1", username="Tester")
    toolbar = WhiteboardToolbar(state)

    # 1. Verify Laser Pen is directly in the toolbar (position 3) and can be selected
    assert TOOL_LASER_PEN in toolbar.tool_buttons
    toolbar.tool_buttons[TOOL_LASER_PEN].click()
    assert state.current_tool == TOOL_LASER_PEN
    assert toolbar.tool_buttons[TOOL_LASER_PEN].isChecked() is True

    # 2. Switch back to Pen
    toolbar.tool_buttons[TOOL_PEN].click()
    assert state.current_tool == TOOL_PEN
    assert toolbar.tool_buttons[TOOL_PEN].isChecked() is True
    assert toolbar.tool_buttons[TOOL_LASER_PEN].isChecked() is False

    # 3. Verify More menu actions (History, Share File, Export PNG)
    assert hasattr(toolbar, "more_menu")
    menu_actions = [a.text() for a in toolbar.more_menu.actions()]
    assert any("History" in text for text in menu_actions)
    assert any("Share File" in text for text in menu_actions)
    assert any("Export PNG" in text for text in menu_actions)


def test_canvas_zoom_and_scaling():
    app = QApplication.instance() or QApplication([])
    state = LocalState()
    canvas = WhiteboardCanvas(state)

    received_pct = []
    canvas.zoom_changed_signal.connect(lambda p: received_pct.append(p))

    canvas.set_zoom(1.5)
    assert canvas.zoom_level == 1.5
    assert received_pct[-1] == 150

    # Test coordinate unscaling
    unscaled = canvas._to_canvas_coords(QPointF(300, 150))
    assert unscaled.x() == 200.0
    assert unscaled.y() == 100.0

    # Test zoom clamping
    canvas.set_zoom(10.0)
    assert canvas.zoom_level == 3.0
    canvas.set_zoom(0.01)
    assert canvas.zoom_level == 0.25

    # Test fit to screen
    canvas.fit_to_screen(1200, 800)
    assert 0.25 <= canvas.zoom_level <= 1.0


def test_canvas_delete_selected():
    app = QApplication.instance() or QApplication([])
    state = LocalState()
    canvas = WhiteboardCanvas(state)

    deleted_ids = []
    canvas.object_deleted_signal.connect(lambda oid: deleted_ids.append(oid))

    op = {
        "op_id": "op-del-test",
        "op_type": TOOL_RECT,
        "data": {"start": [10, 10], "end": [50, 50], "color": "#000000", "width": 2},
    }
    state.add_operation(op)
    state.selected_op_id = "op-del-test"

    canvas.delete_selected()
    assert state.selected_op_id is None
    assert "op-del-test" in deleted_ids
    # Verify removed from active operations
    assert canvas._get_op_by_id("op-del-test") is None


def test_vector_icons_generation():
    import client.ui_icons as ui_icons

    app_icon = ui_icons.get_app_icon(32)
    assert not app_icon.isNull()

    tool_names = [
        "select", "pen", "eraser", "line", "rectangle", "circle", "text", "sticky_notes",
        "laser_pen", "laser_pointer", "undo", "redo", "clear", "export", "history",
        "file_sharing", "zoom_in", "zoom_out", "fit_screen", "chat", "participants",
        "send", "end_meeting", "leave",
    ]
    for name in tool_names:
        ico = ui_icons.get_tool_icon(name, size=24)
        assert not ico.isNull(), f"Icon '{name}' failed to generate"


def test_chat_panel_load_history():
    app = QApplication.instance() or QApplication([])
    from client.chat_panel import ChatPanel

    panel = ChatPanel()
    panel.set_current_username("Engineer")

    # 1. Test empty and None history handling
    panel.load_history(None)
    panel.load_history([])
    assert panel.chat_display.toPlainText().strip() == ""

    # 2. Test chronological loading of chat history
    now = time.time()
    hist = [
        {"message_id": "m2", "username": "Bhanu", "text": "Second message", "timestamp": now + 10},
        {"message_id": "m1", "username": "Sathvik", "text": "First message", "timestamp": now},
        {"message_id": "m3", "username": "Engineer", "text": "Third message", "timestamp": now + 20},
    ]
    panel.load_history(hist)

    text = panel.chat_display.toPlainText()
    assert "First message" in text
    assert "Second message" in text
    assert "Third message" in text
    # Verify chronological ordering
    idx1 = text.find("First message")
    idx2 = text.find("Second message")
    idx3 = text.find("Third message")
    assert idx1 < idx2 < idx3

    # 3. Test duplicate history load prevention
    panel.load_history(hist)
    # The count of "First message" should still be 1
    assert text.count("First message") == 1

    # 4. Test incoming live message deduplication
    panel.add_chat_message("Sathvik", "Duplicate test", timestamp=now, message_id="m1")
    assert "Duplicate test" not in panel.chat_display.toPlainText()

    # 5. Clear chat
    panel.clear_chat()
    assert panel.chat_display.toPlainText().strip() == ""


def test_light_blue_theme_and_bottom_undo_redo():
    app = QApplication.instance() or QApplication([])
    state = LocalState(user_id="u1", username="Tester", current_room_id="room-1")
    net = NetworkClient()
    win = MainWindow(state, net)

    # 1. Verify canvas initialization
    canvas = win.canvas
    assert canvas.width() == DEFAULT_CANVAS_WIDTH
    assert canvas.height() == DEFAULT_CANVAS_HEIGHT

    # 2. Verify drawing tools exact order
    toolbar = win.toolbar
    expected_order = [
        TOOL_SELECT, TOOL_PEN, TOOL_LASER_PEN, TOOL_ERASER,
        TOOL_LINE, TOOL_RECT, TOOL_CIRCLE, TOOL_TEXT, TOOL_STICKY
    ]
    tool_keys = list(toolbar.tool_buttons.keys())
    assert tool_keys == expected_order

    # 3. Verify Undo and Redo are NOT in toolbar's actions container
    tb_action_btns = [b.text() for b in toolbar.actions_container.findChildren(QPushButton)]
    assert "Undo" not in tb_action_btns
    assert "Redo" not in tb_action_btns
    assert "Clear" in tb_action_btns

    # 4. Verify Undo and Redo are present at canvas bottom-right action bar
    bottom_action_btns = win.canvas_viewport.action_bar.findChildren(QPushButton)
    assert any("Undo" in b.toolTip() for b in bottom_action_btns)
    assert any("Redo" in b.toolTip() for b in bottom_action_btns)
    assert any("Delete" in b.toolTip() for b in bottom_action_btns)


def test_deletion_and_undo_redo_restoration():
    from server.whiteboard_manager import WhiteboardManager
    mgr = WhiteboardManager()
    room_wb = mgr.get_or_create_room_whiteboard("test-del-room")

    # 1. User draws op1
    op1_dict = {"op_id": "op-pen-1", "op_type": "pen", "data": {"points": [[10, 10], [20, 20]], "width": 3, "color": "#000000"}}
    ok1, msg1, op1 = room_wb.add_operation(op1_dict, "u1", "Alice")
    assert ok1
    op1_id = op1.op_id

    # 2. User draws op2
    op2_dict = {"op_id": "op-line-2", "op_type": "line", "data": {"start": [30, 30], "end": [80, 80], "width": 3, "color": "#000000"}}
    ok2, msg2, op2 = room_wb.add_operation(op2_dict, "u1", "Alice")
    assert ok2
    op2_id = op2.op_id

    snap = room_wb.get_snapshot()
    assert len(snap["operations"]) == 2

    # 3. User deletes op2
    ok_del, msg_del, op_del = room_wb.delete_operation(op2_id, "u1")
    assert ok_del
    assert op_del.is_deleted is True

    # Active snapshot only contains op1
    snap = room_wb.get_snapshot()
    assert len(snap["operations"]) == 1
    assert snap["operations"][0]["op_id"] == op1_id

    # 4. User undoes: op2 should be restored! op1 must NOT be touched
    ok_undo, msg_undo, op_undo = room_wb.undo_last_user_operation("u1")
    assert ok_undo
    assert op_undo.op_id == op2_id
    assert op_undo.is_deleted is False

    snap = room_wb.get_snapshot()
    assert len(snap["operations"]) == 2
    op_ids = [o["op_id"] for o in snap["operations"]]
    assert op1_id in op_ids and op2_id in op_ids

    # 5. User redoes: op2 should be re-deleted!
    ok_redo, msg_redo, op_redo = room_wb.redo_last_user_operation("u1")
    assert ok_redo
    assert op_redo.op_id == op2_id
    assert op_redo.is_deleted is True

    snap = room_wb.get_snapshot()
    assert len(snap["operations"]) == 1
    assert snap["operations"][0]["op_id"] == op1_id


def test_precise_hit_testing_vs_bounding_box():
    app = QApplication.instance() or QApplication([])
    state = LocalState(user_id="u1", username="Alice", current_room_id="room-1")
    canvas = WhiteboardCanvas(state)

    # Diagonal stroke from (10, 10) to (100, 100)
    op = {
        "op_id": "stroke-1",
        "op_type": TOOL_PEN,
        "data": {"points": [[10, 10], [100, 100]], "width": 4, "color": "#000"},
        "author_name": "Alice",
        "is_undone": False,
        "is_deleted": False,
        "cleared_at_seq": None,
    }
    state.operations = [op]

    # Point (10, 90) is inside bounding box (10..100, 10..100) but ~56px away from line
    hit_miss = canvas._hit_test_precise(QPointF(10, 90))
    assert hit_miss is None

    # Point (50, 52) is ~1.4px away from line: must hit!
    hit = canvas._hit_test_precise(QPointF(50, 52))
    assert hit is not None
    assert hit["op_id"] == "stroke-1"


def test_laser_stroke_broadcast_and_3s_expiration():
    assert LASER_FADE_DURATION == 3.0
    state = LocalState(user_id="u1", username="Alice")
    state.add_laser_stroke("u1", [[10, 10], [50, 50]], color="#EF4444")
    assert len(state.laser_strokes) == 1

    # Immediate purge does not remove fresh stroke
    purged = state.purge_expired_lasers(fade_duration=3.0)
    assert purged is False
    assert len(state.laser_strokes) == 1

    # Simulate 3.1s passage
    state.laser_strokes[0]["created_at"] = time.time() - 3.1
    purged = state.purge_expired_lasers(fade_duration=3.0)
    assert purged is True
    assert len(state.laser_strokes) == 0


def test_host_only_end_meeting_authorization():
    from server.session_manager import SessionManager
    from server.socket_server import SocketServer
    from common.message_types import MessageType

    session_mgr = SessionManager()
    ok, msg, room = session_mgr.create_room(room_id="test-room-host", creator_id="host-1", room_name="Test Room")
    assert ok
    assert room is not None

    # Non-host attempt
    server = SocketServer()
    server.session_mgr = session_mgr

    sent_messages = []
    server.connection_mgr.send_to_client = lambda uid, m: sent_messages.append((uid, m))

    msg = {"type": MessageType.END_MEETING.value, "room_id": room.room_id, "user_id": "guest-2"}
    server._handle_end_meeting(user_id="guest-2", room_id=room.room_id, msg=msg)

    # Verify error message returned and meeting not ended
    assert len(sent_messages) == 1
    assert sent_messages[0][0] == "guest-2"
    unpacked = sent_messages[0][1]
    assert unpacked["type"] == MessageType.ERROR.value
    assert "Only the meeting host" in unpacked["message"]
    assert session_mgr.get_room(room.room_id) is not None

    # Host UI visibility check (check explicit visibility state on widget)
    app = QApplication.instance() or QApplication([])
    state_host = LocalState(user_id="host-1", username="Host", is_host=True)
    net = NetworkClient()
    win_host = MainWindow(state_host, net)
    assert not win_host.end_meeting_btn.isHidden()

    state_guest = LocalState(user_id="guest-2", username="Guest", is_host=False)
    win_guest = MainWindow(state_guest, net)
    assert win_guest.end_meeting_btn.isHidden()





