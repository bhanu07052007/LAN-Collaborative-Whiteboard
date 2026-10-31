"""
Canvas Widget for Collaborative Whiteboard.
Renders shared drawing operations, text objects, sticky notes, and laser presentations.
Supports object selection, moving, resizing, and deleting with PySide6 QPainter.
Handles mandatory author attribution ('Written by: <username>'), dynamic zooming (25% to 300%),
fit-to-screen scaling, and PNG export.
"""

import math
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QWidget

from client.dialogs import StickyNoteDialog, TextInputDialog

from common.constants import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    LASER_COLOR,
    LASER_FADE_DURATION,
    TOOL_CIRCLE,
    TOOL_ERASER,
    TOOL_LASER_PEN,
    TOOL_LASER_POINTER,
    TOOL_LINE,
    TOOL_PEN,
    TOOL_RECT,
    TOOL_SELECT,
    TOOL_STICKY,
    TOOL_TEXT,
)
from client.local_state import LocalState


class WhiteboardCanvas(QWidget):
    # Signals emitted to parent / network
    operation_completed_signal = Signal(str, dict, str)  # op_type, data, op_id
    object_modified_signal = Signal(str, dict)           # op_id, new_data
    object_deleted_signal = Signal(str)                  # op_id
    laser_stroke_signal = Signal(list, str)              # points, color
    laser_pointer_signal = Signal(float, float, bool)    # x, y, active
    zoom_changed_signal = Signal(int)                    # zoom percentage (e.g. 100)

    def __init__(self, local_state: LocalState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = local_state

        self.canvas_width = DEFAULT_CANVAS_WIDTH
        self.canvas_height = DEFAULT_CANVAS_HEIGHT
        self.zoom_level: float = 1.0

        self.setFixedSize(self.canvas_width, self.canvas_height)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # In-progress drawing state
        self._is_drawing = False
        self._current_points: List[List[float]] = []
        self._start_pos: Optional[QPointF] = None
        self._current_pos: Optional[QPointF] = None

        # Selection and manipulation state
        self._is_dragging_object = False
        self._resizing_handle: Optional[str] = None
        self._drag_start_pos: Optional[QPointF] = None
        self._original_op_data: Optional[Dict[str, Any]] = None

        self._min_dist_sq = 4.0  # 2 pixels distance threshold for smoothing
        self.setMouseTracking(True)

        # Animation timer for fading laser strokes
        self._laser_timer = QTimer(self)
        self._laser_timer.setInterval(40)  # 25 fps
        self._laser_timer.timeout.connect(self._on_laser_timer_tick)
        self._laser_timer.start()

    def _to_canvas_coords(self, pos: QPointF) -> QPointF:
        """Converts viewport mouse position into unscaled canvas coordinate space."""
        return QPointF(pos.x() / self.zoom_level, pos.y() / self.zoom_level)

    def set_zoom(self, zoom: float) -> None:
        """Sets canvas zoom factor between 25% and 300%."""
        zoom = max(0.25, min(3.0, zoom))
        self.zoom_level = zoom
        self.setFixedSize(int(self.canvas_width * self.zoom_level), int(self.canvas_height * self.zoom_level))
        self.zoom_changed_signal.emit(int(round(self.zoom_level * 100)))
        self.update()

    def zoom_in(self) -> None:
        self.set_zoom(round(self.zoom_level + 0.1, 2))

    def zoom_out(self) -> None:
        self.set_zoom(round(self.zoom_level - 0.1, 2))

    def fit_to_screen(self, viewport_width: int, viewport_height: int) -> None:
        """Scales canvas to comfortably fit inside the visible scroll viewport."""
        margin = 32
        avail_w = max(100, viewport_width - margin)
        avail_h = max(100, viewport_height - margin)
        scale_w = avail_w / self.canvas_width
        scale_h = avail_h / self.canvas_height
        zoom = min(scale_w, scale_h, 1.0)
        self.set_zoom(round(zoom, 2))

    def delete_selected(self) -> None:
        """Deletes currently selected object from active canvas."""
        if self.state.selected_op_id:
            op_id = self.state.selected_op_id
            self.state.delete_operation(op_id)
            self.state.selected_op_id = None
            self.object_deleted_signal.emit(op_id)
            self.update()

    def _on_laser_timer_tick(self) -> None:
        if self.state.purge_expired_lasers(LASER_FADE_DURATION):
            self.update()

    def keyPressEvent(self, event) -> None:
        """Handles keyboard shortcuts like Delete key for selected objects."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = self._to_canvas_coords(event.position())
        tool = self.state.current_tool

        # 1. Selection Tool Logic
        if tool == TOOL_SELECT:
            self._handle_select_press(pos)
            return

        # 2. Text Tool Logic
        if tool == TOOL_TEXT:
            self._handle_text_tool_click(pos)
            return

        # 3. Sticky Note Tool Logic
        if tool == TOOL_STICKY:
            self._handle_sticky_tool_click(pos)
            return

        # 4. Laser Pen Logic
        if tool == TOOL_LASER_PEN:
            self._is_drawing = True
            self._current_points = [[round(pos.x(), 1), round(pos.y(), 1)]]
            self.update()
            return

        # 5. Standard Drawing Tools (Pen, Eraser, Line, Rect, Circle)
        self._is_drawing = True
        self._start_pos = pos
        self._current_pos = pos
        if tool in (TOOL_PEN, TOOL_ERASER):
            self._current_points = [[round(pos.x(), 1), round(pos.y(), 1)]]

        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = self._to_canvas_coords(event.position())
        self._current_pos = pos
        tool = self.state.current_tool

        if tool == TOOL_SELECT:
            if self._is_dragging_object or self._resizing_handle:
                self._handle_select_move(pos)
                self.update()
            return

        if not self._is_drawing:
            return

        if tool in (TOOL_PEN, TOOL_ERASER, TOOL_LASER_PEN):
            last = self._current_points[-1]
            dx = pos.x() - last[0]
            dy = pos.y() - last[1]
            if (dx * dx + dy * dy) >= self._min_dist_sq:
                self._current_points.append([round(pos.x(), 1), round(pos.y(), 1)])
                self.update()
        else:
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = self._to_canvas_coords(event.position())
        tool = self.state.current_tool

        if tool == TOOL_SELECT:
            self._handle_select_release()
            self.update()
            return

        if not self._is_drawing:
            return

        self._is_drawing = False

        if tool == TOOL_LASER_PEN:
            if len(self._current_points) >= 2:
                self.state.add_laser_stroke(self.state.user_id, self._current_points, LASER_COLOR)
                self.laser_stroke_signal.emit(self._current_points, LASER_COLOR)
            self._current_points = []
            self.update()
            return

        # Commit permanent drawing operation
        op_id = f"op-{uuid.uuid4().hex[:12]}"
        data: Dict[str, Any] = {}

        if tool in (TOOL_PEN, TOOL_ERASER):
            if len(self._current_points) >= 1:
                color = "#FFFFFF" if tool == TOOL_ERASER else self.state.current_color
                width = self.state.eraser_size if tool == TOOL_ERASER else self.state.brush_size
                data = {
                    "points": self._current_points,
                    "color": color,
                    "width": width,
                }
                self.operation_completed_signal.emit(tool, data, op_id)
            self._current_points = []

        elif tool in (TOOL_LINE, TOOL_RECT, TOOL_CIRCLE) and self._start_pos:
            data = {
                "start": [round(self._start_pos.x(), 1), round(self._start_pos.y(), 1)],
                "end": [round(pos.x(), 1), round(pos.y(), 1)],
                "color": self.state.current_color,
                "width": self.state.brush_size,
            }
            self.operation_completed_signal.emit(tool, data, op_id)

        self._start_pos = None
        self._current_pos = None
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double clicking a text object or sticky note allows quick in-place editing."""
        pos = self._to_canvas_coords(event.position())
        hit_op = self._hit_test(pos)
        if not hit_op:
            return

        op_type = hit_op.get("op_type")
        data = hit_op.get("data", {})
        op_id = hit_op.get("op_id")

        if op_type == TOOL_TEXT:
            new_text, ok = TextInputDialog.getText(
                self,
                "Edit Text",
                "Update text content:",
                text=data.get("text", ""),
            )
            if ok and new_text.strip():
                data["text"] = new_text.strip()
                self.object_modified_signal.emit(op_id, data)
                self.update()

        elif op_type == TOOL_STICKY:
            new_text, ok = StickyNoteDialog.getStickyText(
                self,
                "Edit Sticky Note",
                "Update sticky note content:",
                text=data.get("text", ""),
            )
            if ok and new_text.strip():
                data["text"] = new_text.strip()
                self.object_modified_signal.emit(op_id, data)
                self.update()

    def _handle_text_tool_click(self, pos: QPointF) -> None:
        text, ok = TextInputDialog.getText(
            self,
            "Insert Text",
            "Enter text to place on whiteboard (Author attribution will be attached):",
        )
        if ok and text.strip():
            op_id = f"op-{uuid.uuid4().hex[:12]}"
            data = {
                "x": round(pos.x(), 1),
                "y": round(pos.y(), 1),
                "text": text.strip(),
                "color": self.state.current_color,
                "font_size": 16,
            }
            self.operation_completed_signal.emit(TOOL_TEXT, data, op_id)

    def _handle_sticky_tool_click(self, pos: QPointF) -> None:
        text, ok = StickyNoteDialog.getStickyText(
            self,
            "New Sticky Note",
            "Enter sticky note content:",
            "",
        )
        if ok and text.strip():
            op_id = f"op-{uuid.uuid4().hex[:12]}"
            data = {
                "x": round(pos.x(), 1),
                "y": round(pos.y(), 1),
                "width": 180,
                "height": 140,
                "text": text.strip(),
                "color": self.state.sticky_color,
            }
            self.operation_completed_signal.emit(TOOL_STICKY, data, op_id)

    # -------------------------------------------------------------------------
    # Object Selection, Move, Resize Logic
    # -------------------------------------------------------------------------

    def _handle_select_press(self, pos: QPointF) -> None:
        if self.state.selected_op_id:
            sel_op = self._get_op_by_id(self.state.selected_op_id)
            if sel_op:
                handle = self._get_handle_at(sel_op, pos)
                if handle:
                    self._resizing_handle = handle
                    self._drag_start_pos = pos
                    self._original_op_data = dict(sel_op.get("data", {}))
                    return

        hit_op = self._hit_test(pos)
        if hit_op:
            self.state.selected_op_id = hit_op.get("op_id")
            self._is_dragging_object = True
            self._drag_start_pos = pos
            self._original_op_data = dict(hit_op.get("data", {}))
        else:
            self.state.selected_op_id = None
            self._is_dragging_object = False
            self._resizing_handle = None

        self.update()

    def _handle_select_move(self, pos: QPointF) -> None:
        if not self.state.selected_op_id or not self._drag_start_pos:
            return

        op = self._get_op_by_id(self.state.selected_op_id)
        if not op:
            return

        data = op.get("data", {})
        op_type = op.get("op_type")
        dx = pos.x() - self._drag_start_pos.x()
        dy = pos.y() - self._drag_start_pos.y()
        self._drag_start_pos = pos

        # Moving object
        if self._is_dragging_object:
            if op_type in (TOOL_TEXT, TOOL_STICKY):
                data["x"] = round(data.get("x", 0) + dx, 1)
                data["y"] = round(data.get("y", 0) + dy, 1)
            elif op_type in (TOOL_LINE, TOOL_RECT, TOOL_CIRCLE):
                start = data.get("start", [0, 0])
                end = data.get("end", [0, 0])
                data["start"] = [round(start[0] + dx, 1), round(start[1] + dy, 1)]
                data["end"] = [round(end[0] + dx, 1), round(end[1] + dy, 1)]
            elif op_type in (TOOL_PEN, TOOL_ERASER):
                pts = data.get("points", [])
                for pt in pts:
                    pt[0] = round(pt[0] + dx, 1)
                    pt[1] = round(pt[1] + dy, 1)

        # Resizing object
        elif self._resizing_handle:
            if op_type == TOOL_STICKY:
                w = data.get("width", 180)
                h = data.get("height", 140)
                if self._resizing_handle in ("br", "r", "b"):
                    data["width"] = max(80, round(w + dx, 1))
                    data["height"] = max(60, round(h + dy, 1))
            elif op_type in (TOOL_RECT, TOOL_CIRCLE, TOOL_LINE):
                end = data.get("end", [0, 0])
                data["end"] = [round(end[0] + dx, 1), round(end[1] + dy, 1)]

    def _handle_select_release(self) -> None:
        if (self._is_dragging_object or self._resizing_handle) and self.state.selected_op_id:
            op = self._get_op_by_id(self.state.selected_op_id)
            if op:
                self.object_modified_signal.emit(op["op_id"], op.get("data", {}))

        self._is_dragging_object = False
        self._resizing_handle = None
        self._drag_start_pos = None
        self._original_op_data = None

    def _get_op_by_id(self, op_id: str) -> Optional[Dict[str, Any]]:
        for op in self.state.operations:
            if op.get("op_id") == op_id and not op.get("is_undone", False) and op.get("cleared_at_seq") is None and not op.get("is_deleted", False):
                return op
        return None

    def _get_op_bounding_rect(self, op: Dict[str, Any]) -> QRectF:
        op_type = op.get("op_type")
        data = op.get("data", {})

        if op_type == TOOL_STICKY:
            return QRectF(data.get("x", 0), data.get("y", 0), data.get("width", 180), data.get("height", 140))

        if op_type == TOOL_TEXT:
            text = data.get("text", "")
            lines = text.count("\n") + 1
            w = max(120, len(text) * 9)
            h = lines * 24 + 30
            return QRectF(data.get("x", 0), data.get("y", 0), w, h)

        if op_type in (TOOL_LINE, TOOL_RECT, TOOL_CIRCLE):
            start = data.get("start", [0, 0])
            end = data.get("end", [0, 0])
            x = min(start[0], end[0])
            y = min(start[1], end[1])
            w = max(10, abs(end[0] - start[0]))
            h = max(10, abs(end[1] - start[1]))
            return QRectF(x, y, w, h)

        if op_type in (TOOL_PEN, TOOL_ERASER):
            pts = data.get("points", [])
            if not pts:
                return QRectF()
            min_x = min(p[0] for p in pts)
            max_x = max(p[0] for p in pts)
            min_y = min(p[1] for p in pts)
            max_y = max(p[1] for p in pts)
            return QRectF(min_x, min_y, max(10, max_x - min_x), max(10, max_y - min_y))

        return QRectF()

    def _hit_test(self, pos: QPointF) -> Optional[Dict[str, Any]]:
        for op in reversed(self.state.operations):
            if op.get("is_undone", False) or op.get("cleared_at_seq") is not None or op.get("is_deleted", False):
                continue
            rect = self._get_op_bounding_rect(op)
            if rect.adjusted(-6, -6, 6, 6).contains(pos):
                return op
        return None

    def _get_handle_at(self, op: Dict[str, Any], pos: QPointF) -> Optional[str]:
        rect = self._get_op_bounding_rect(op)
        br = QPointF(rect.right(), rect.bottom())
        if (pos.x() - br.x()) ** 2 + (pos.y() - br.y()) ** 2 <= 64:  # 8px radius
            return "br"
        return None

    # -------------------------------------------------------------------------
    # Painting and Rendering
    # -------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 1. Background
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        painter.save()
        painter.scale(self.zoom_level, self.zoom_level)

        # 2. Subtle dotted canvas grid
        self._draw_grid(painter)

        # 3. Operations
        ops_to_draw = self.state.operations
        if self.state.is_in_history_mode:
            ops_to_draw = self.state.operations[: self.state.history_view_index + 1]

        for op in ops_to_draw:
            if op.get("is_undone", False) or op.get("cleared_at_seq") is not None or op.get("is_deleted", False):
                continue
            self._render_operation(painter, op)

        # 4. Selection boundary and resize handles
        if self.state.current_tool == TOOL_SELECT and self.state.selected_op_id:
            sel_op = self._get_op_by_id(self.state.selected_op_id)
            if sel_op:
                self._render_selection(painter, sel_op)

        # 5. Local in-progress preview stroke or shape
        if self._is_drawing:
            self._render_preview(painter)

        # 6. Ephemeral Laser Pen Strokes
        self._render_laser_strokes(painter)

        # 7. Remote Laser Pointers
        self._render_laser_pointers(painter)

        # 8. History Replay Watermark Banner
        if self.state.is_in_history_mode:
            self._render_history_banner(painter)

        painter.restore()
        painter.end()

    def _draw_grid(self, painter: QPainter) -> None:
        grid_step = 32
        dot_color = QColor("#CBD5E1")
        painter.setPen(QPen(dot_color, 1.4))
        for x in range(grid_step, self.canvas_width, grid_step):
            for y in range(grid_step, self.canvas_height, grid_step):
                painter.drawPoint(x, y)

    def _render_operation(self, painter: QPainter, op: Dict[str, Any]) -> None:
        op_type = op.get("op_type")
        data = op.get("data", {})
        width = data.get("width", 3)
        color_hex = data.get("color", "#000000")

        pen = QPen(QColor(color_hex), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if op_type in (TOOL_PEN, TOOL_ERASER):
            points = data.get("points", [])
            if len(points) >= 2:
                path = QPainterPath()
                path.moveTo(points[0][0], points[0][1])
                for pt in points[1:]:
                    path.lineTo(pt[0], pt[1])
                painter.drawPath(path)
            elif len(points) == 1:
                painter.drawPoint(QPointF(points[0][0], points[0][1]))

        elif op_type == TOOL_LINE:
            start = data.get("start", [0, 0])
            end = data.get("end", [0, 0])
            painter.drawLine(QPointF(start[0], start[1]), QPointF(end[0], end[1]))

        elif op_type == TOOL_RECT:
            start = data.get("start", [0, 0])
            end = data.get("end", [0, 0])
            x = min(start[0], end[0])
            y = min(start[1], end[1])
            w = abs(end[0] - start[0])
            h = abs(end[1] - start[1])
            painter.drawRect(QRectF(x, y, w, h))

        elif op_type == TOOL_CIRCLE:
            start = data.get("start", [0, 0])
            end = data.get("end", [0, 0])
            x = min(start[0], end[0])
            y = min(start[1], end[1])
            w = abs(end[0] - start[0])
            h = abs(end[1] - start[1])
            painter.drawEllipse(QRectF(x, y, w, h))

        # Text Tool with Mandatory Author Attribution
        elif op_type == TOOL_TEXT:
            text = data.get("text", "")
            x = data.get("x", 0)
            y = data.get("y", 0)
            font_size = data.get("font_size", 16)

            painter.setFont(QFont("Segoe UI", font_size, QFont.Weight.Medium))
            painter.setPen(QColor(color_hex))
            painter.drawText(QPointF(x, y + font_size), text)

            # Mandatory Author Attribution
            author = op.get("author_name") or op.get("username") or "Unknown"
            author_tag = f"Written by: {author}"
            author_font = QFont("Segoe UI", 9)
            author_font.setItalic(True)
            painter.setFont(author_font)
            painter.setPen(QColor("#64748B"))
            lines_count = text.count("\n") + 1
            painter.drawText(QPointF(x, y + font_size + lines_count * 20), author_tag)

        # Sticky Notes with Mandatory Author Attribution
        elif op_type == TOOL_STICKY:
            x = data.get("x", 0)
            y = data.get("y", 0)
            w = data.get("width", 180)
            h = data.get("height", 140)
            rect = QRectF(x, y, w, h)
            bg_col = QColor(data.get("color", "#FEF08A"))

            # Note drop shadow
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 25))
            painter.drawRoundedRect(QRectF(x + 3, y + 3, w, h), 8, 8)

            # Note background & border
            painter.setPen(QPen(bg_col.darker(115), 1))
            painter.setBrush(QBrush(bg_col))
            painter.drawRoundedRect(rect, 8, 8)

            # Note content
            text = data.get("text", "")
            painter.setFont(QFont("Segoe UI", 11))
            painter.setPen(QColor("#1E293B"))
            text_rect = QRectF(x + 10, y + 10, w - 20, h - 35)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, text)

            # Mandatory Author Attribution
            author = op.get("author_name") or op.get("username") or "Unknown"
            author_tag = f"Written by: {author}"
            author_font = QFont("Segoe UI", 9)
            author_font.setItalic(True)
            painter.setFont(author_font)
            painter.setPen(QColor("#475569"))
            author_rect = QRectF(x + 10, y + h - 22, w - 20, 16)
            painter.drawText(author_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, author_tag)

    def _render_selection(self, painter: QPainter, op: Dict[str, Any]) -> None:
        rect = self._get_op_bounding_rect(op).adjusted(-4, -4, 4, 4)

        # Dashed selection outline
        pen = QPen(QColor("#594BFA"), 1.8, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

        # Resize handle at bottom-right
        handle_rect = QRectF(rect.right() - 6, rect.bottom() - 6, 12, 12)
        painter.setPen(QPen(QColor("#594BFA"), 2))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawRect(handle_rect)

    def _render_preview(self, painter: QPainter) -> None:
        tool = self.state.current_tool

        if tool in (TOOL_PEN, TOOL_ERASER):
            if len(self._current_points) >= 2:
                color = "#FFFFFF" if tool == TOOL_ERASER else self.state.current_color
                width = self.state.eraser_size if tool == TOOL_ERASER else self.state.brush_size
                pen = QPen(QColor(color), width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)

                path = QPainterPath()
                path.moveTo(self._current_points[0][0], self._current_points[0][1])
                for pt in self._current_points[1:]:
                    path.lineTo(pt[0], pt[1])
                painter.drawPath(path)

        elif tool == TOOL_LASER_PEN:
            if len(self._current_points) >= 2:
                self._draw_glowing_stroke(painter, self._current_points, LASER_COLOR, alpha_mult=1.0)

        elif self._start_pos and self._current_pos:
            pen = QPen(QColor(self.state.current_color), self.state.brush_size)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            if tool == TOOL_LINE:
                painter.drawLine(self._start_pos, self._current_pos)
            elif tool == TOOL_RECT:
                x = min(self._start_pos.x(), self._current_pos.x())
                y = min(self._start_pos.y(), self._current_pos.y())
                w = abs(self._current_pos.x() - self._start_pos.x())
                h = abs(self._current_pos.y() - self._start_pos.y())
                painter.drawRect(QRectF(x, y, w, h))
            elif tool == TOOL_CIRCLE:
                x = min(self._start_pos.x(), self._current_pos.x())
                y = min(self._start_pos.y(), self._current_pos.y())
                w = abs(self._current_pos.x() - self._start_pos.x())
                h = abs(self._current_pos.y() - self._start_pos.y())
                painter.drawEllipse(QRectF(x, y, w, h))

    def _render_laser_strokes(self, painter: QPainter) -> None:
        now = time.time()
        for stroke in self.state.laser_strokes:
            pts = stroke.get("points", [])
            color = stroke.get("color", LASER_COLOR)
            created_at = stroke.get("created_at", now)
            age = now - created_at
            if age >= LASER_FADE_DURATION:
                continue

            alpha_mult = max(0.0, 1.0 - (age / LASER_FADE_DURATION))
            self._draw_glowing_stroke(painter, pts, color, alpha_mult)

    def _draw_glowing_stroke(self, painter: QPainter, points: List[List[float]], color_hex: str, alpha_mult: float) -> None:
        if len(points) < 2:
            return

        path = QPainterPath()
        path.moveTo(points[0][0], points[0][1])
        for pt in points[1:]:
            path.lineTo(pt[0], pt[1])

        # Outer soft glow
        glow_pen = QPen(QColor(239, 68, 68, int(80 * alpha_mult)), 12)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(glow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Core bright stroke
        core_pen = QPen(QColor(255, 255, 255, int(240 * alpha_mult)), 3)
        core_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        core_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(core_pen)
        painter.drawPath(path)

    def _render_laser_pointers(self, painter: QPainter) -> None:
        now = time.time()
        for uid, ptr in self.state.laser_pointers.items():
            if not ptr.get("active", False):
                continue
            if now - ptr.get("timestamp", now) > 5.0:
                continue

            x = ptr.get("x", 0)
            y = ptr.get("y", 0)
            username = ptr.get("username", "Participant")

            # Outer glow
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(239, 68, 68, 90))
            painter.drawEllipse(QPointF(x, y), 12, 12)

            # Bright core dot
            painter.setBrush(QColor(239, 68, 68, 255))
            painter.drawEllipse(QPointF(x, y), 5, 5)

            # Name tag badge
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            badge_rect = QRectF(x + 10, y - 8, max(60, len(username) * 8 + 12), 20)
            painter.setBrush(QColor(15, 23, 42, 220))
            painter.drawRoundedRect(badge_rect, 6, 6)

            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, username)

    def _render_history_banner(self, painter: QPainter) -> None:
        total = len(self.state.operations)
        curr = min(total, self.state.history_view_index + 1)
        banner_text = f"Historical Replay Mode (Operation {curr} / {total}) - Read Only"

        banner_rect = QRectF(20, 20, 480, 36)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(245, 158, 11, 230))
        painter.drawRoundedRect(banner_rect, 8, 8)

        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(banner_rect, Qt.AlignmentFlag.AlignCenter, banner_text)

    def export_to_png(self, file_path: str) -> bool:
        """Exports the entire canvas representation to a high-resolution PNG image file."""
        image = QImage(self.canvas_width, self.canvas_height, QImage.Format.Format_ARGB32)
        image.fill(QColor("#FFFFFF"))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        for op in self.state.operations:
            if op.get("is_undone", False) or op.get("cleared_at_seq") is not None or op.get("is_deleted", False):
                continue
            self._render_operation(painter, op)

        painter.end()
        return image.save(file_path, "PNG")
