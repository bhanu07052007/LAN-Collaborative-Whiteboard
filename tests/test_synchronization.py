"""
Unit tests for Real-Time Drawing Synchronization, Operation Sequencing,
Concurrency Handling, Undo/Redo, and Snapshot Generation.
"""

import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pytest
except ImportError:
    pytest = None

from common.constants import TOOL_LINE, TOOL_PEN, TOOL_RECT
from server.whiteboard_manager import RoomWhiteboard, WhiteboardManager


def test_operation_validation():
    wb = RoomWhiteboard("room-test")

    # Valid pen operation
    valid_op = {
        "op_type": TOOL_PEN,
        "data": {
            "points": [[10, 20], [15, 25], [20, 30]],
            "color": "#3B82F6",
            "width": 3,
        },
    }
    ok, err, op = wb.add_operation(valid_op, "user-1", "Alice")
    assert ok
    assert op.seq_num == 1
    assert op.op_type == TOOL_PEN

    # Invalid tool
    bad_tool = {"op_type": "magic_wand", "data": {"width": 3, "color": "#000000"}}
    ok_b1, err_b1, _ = wb.add_operation(bad_tool, "user-1", "Alice")
    assert not ok_b1

    # Invalid brush width
    bad_width = {"op_type": TOOL_PEN, "data": {"points": [[0, 0]], "color": "#000000", "width": 999}}
    ok_b2, err_b2, _ = wb.add_operation(bad_width, "user-1", "Alice")
    assert not ok_b2

    # Invalid color
    bad_color = {"op_type": TOOL_PEN, "data": {"points": [[0, 0]], "color": "not-a-color", "width": 3}}
    ok_b3, err_b3, _ = wb.add_operation(bad_color, "user-1", "Alice")
    assert not ok_b3


def test_monotonic_sequence_numbers():
    wb = RoomWhiteboard("room-seq")
    for i in range(10):
        op = {
            "op_type": TOOL_RECT,
            "data": {
                "start": [i * 10, i * 10],
                "end": [i * 10 + 50, i * 10 + 50],
                "color": "#000000",
                "width": 2,
            },
        }
        ok, _, res = wb.add_operation(op, f"user-{i}", f"User {i}")
        assert ok
        assert res.seq_num == (i + 1)

    assert wb.current_seq_num == 10


def test_concurrent_drawing_operations():
    """
    Tests multiple simulated client threads drawing concurrently.
    Guarantees no lost updates and strict sequential sequence numbering.
    """
    wb = RoomWhiteboard("room-concurrent")
    num_threads = 8
    ops_per_thread = 25
    total_expected = num_threads * ops_per_thread

    def worker(thread_idx: int):
        for i in range(ops_per_thread):
            op = {
                "op_type": TOOL_PEN,
                "data": {
                    "points": [[thread_idx * 10, i * 5], [thread_idx * 10 + 2, i * 5 + 2]],
                    "color": "#EF4444",
                    "width": 2,
                },
            }
            wb.add_operation(op, f"user-{thread_idx}", f"Worker-{thread_idx}")

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert wb.current_seq_num == total_expected
    snapshot = wb.get_snapshot()
    assert len(snapshot["operations"]) == total_expected

    # Verify strictly monotonic sequence numbers without duplicates
    seqs = [op["seq_num"] for op in snapshot["operations"]]
    assert seqs == list(range(1, total_expected + 1))


def test_user_specific_undo_and_redo():
    wb = RoomWhiteboard("room-undo")

    # User 1 draws 2 shapes
    wb.add_operation(
        {"op_type": TOOL_RECT, "data": {"start": [0, 0], "end": [10, 10], "color": "#000000", "width": 2}},
        "user-1",
        "Alice",
    )
    wb.add_operation(
        {"op_type": TOOL_RECT, "data": {"start": [20, 20], "end": [30, 30], "color": "#000000", "width": 2}},
        "user-1",
        "Alice",
    )

    # User 2 draws 1 shape
    wb.add_operation(
        {"op_type": TOOL_LINE, "data": {"start": [50, 50], "end": [60, 60], "color": "#FF0000", "width": 3}},
        "user-2",
        "Bob",
    )

    # 3 active ops
    snap = wb.get_snapshot()
    assert len(snap["operations"]) == 3

    # User 1 undoes: should undo Alice's second rect, leaving Bob's line and Alice's first rect active
    ok, _, undone_op = wb.undo_last_user_operation("user-1")
    assert ok
    snap_after_undo = wb.get_snapshot()
    assert len(snap_after_undo["operations"]) == 2
    active_users = [o["user_id"] for o in snap_after_undo["operations"]]
    assert active_users == ["user-1", "user-2"]

    # User 1 redoes: restores Alice's second rect
    ok_r, _, redone_op = wb.redo_last_user_operation("user-1")
    assert ok_r
    assert redone_op.op_id == undone_op.op_id
    snap_after_redo = wb.get_snapshot()
    assert len(snap_after_redo["operations"]) == 3


def test_clear_canvas_and_late_joiner_snapshot():
    wb = RoomWhiteboard("room-clear")

    wb.add_operation(
        {"op_type": TOOL_PEN, "data": {"points": [[1, 1], [2, 2]], "color": "#000000", "width": 2}},
        "user-1",
        "Alice",
    )
    wb.add_operation(
        {"op_type": TOOL_PEN, "data": {"points": [[3, 3], [4, 4]], "color": "#000000", "width": 2}},
        "user-2",
        "Bob",
    )

    assert len(wb.get_snapshot()["operations"]) == 2

    # Clear canvas
    clear_seq, cleared_count = wb.clear_canvas("user-1", "Alice")
    assert cleared_count == 2
    assert wb.current_seq_num == clear_seq

    # Late joiner snapshot should contain 0 active operations
    late_joiner_snap = wb.get_snapshot()
    assert len(late_joiner_snap["operations"]) == 0
    assert late_joiner_snap["seq_num"] == clear_seq
