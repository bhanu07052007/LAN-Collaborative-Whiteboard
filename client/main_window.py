"""
Main Window for Collaborative Whiteboard.
Closely matches the modern commercial product reference design.

Features:
- Dark navy application canvas theme (#080F1C)
- Professional top header with room selector dropdown, connection indicator (#20D6A0),
  user badge with avatar, End Meeting danger button (#E63946), and Leave Session button.
- Dynamic responsive toolbar with intelligent width calculation and More ▾ overflow menu.
- Large white drawing canvas with rounded corners, subtle dot grid, smooth QPainter rendering.
- Floating bottom-left canvas controls: Zoom Out (-), Zoom %, Zoom In (+), Fit to Screen (⛶).
- Floating bottom-right canvas controls: Undo (↶), Redo (↷), Delete selected (🗑).
- Modern dark right sidebar cards: Connected Participants with '+ Add' invite action,
  and Group Chat with distinct participant color badges and paper airplane send button.
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from client.canvas import WhiteboardCanvas
from client.chat_panel import ChatPanel
from client.file_transfer import FileShareDialog, IncomingFileManager
from client.history_panel import HistoryReplayPanel
from client.local_state import LocalState
from client.network_client import NetworkClient
from client.participant_panel import ParticipantPanel
from client.toolbar import WhiteboardToolbar
import client.ui_icons as ui_icons


class CanvasViewportContainer(QWidget):
    """
    Hosts the scrollable whiteboard canvas and anchors floating bottom
    controls (Zoom at bottom-left, Undo/Redo/Delete at bottom-right)
    matching the exact commercial reference design.
    """

    def __init__(
        self,
        canvas: WhiteboardCanvas,
        main_win: "MainWindow",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.canvas = canvas
        self.main_win = main_win

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scroll Area for canvas
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1.5px solid #AFCDF3;
                border-radius: 12px;
                background-color: #FFFFFF;
            }
        """)
        self.scroll_area.setWidget(self.canvas)
        layout.addWidget(self.scroll_area)

        # Floating Bottom-Left Controls: [ - ] 100% [ + ] | [ ⛶ ]
        self.zoom_bar = self._create_zoom_bar()
        self.zoom_bar.setParent(self)

        # Floating Bottom-Right Controls: [ ↶ ] [ ↷ ] | [ 🗑 ]
        self.action_bar = self._create_action_bar()
        self.action_bar.setParent(self)

        # Connect canvas zoom signal to label
        self.canvas.zoom_changed_signal.connect(self._on_zoom_changed)

    def _create_zoom_bar(self) -> QFrame:
        bar = QFrame(self)
        bar.setStyleSheet("""
            QFrame {
                background-color: #F2F7FF;
                border: 1px solid #AFCDF3;
                border-radius: 8px;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                color: #172B4D;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
                min-width: 24px;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #C8DFFF;
                color: #3478F6;
            }
            QLabel {
                background: transparent;
                color: #172B4D;
                font-size: 11px;
                font-weight: 700;
                padding: 0 4px;
            }
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        # Zoom out (-)
        btn_out = QPushButton("−", bar)
        btn_out.setToolTip("Zoom out")
        btn_out.clicked.connect(self.canvas.zoom_out)
        layout.addWidget(btn_out)

        # Percentage label
        self.zoom_lbl = QLabel("100%", bar)
        layout.addWidget(self.zoom_lbl)

        # Zoom in (+)
        btn_in = QPushButton("+", bar)
        btn_in.setToolTip("Zoom in")
        btn_in.clicked.connect(self.canvas.zoom_in)
        layout.addWidget(btn_in)

        # Separator
        sep = QFrame(bar)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("background-color: #AFCDF3; max-width: 1px; min-width: 1px; margin: 2px 2px;")
        layout.addWidget(sep)

        # Fit to screen
        btn_fit = QPushButton(bar)
        btn_fit.setIcon(ui_icons.get_tool_icon("fit_screen", color="#172B4D", size=16))
        btn_fit.setToolTip("Fit canvas to screen")
        btn_fit.clicked.connect(self._on_fit_screen_clicked)
        layout.addWidget(btn_fit)

        bar.adjustSize()
        return bar

    def _create_action_bar(self) -> QFrame:
        bar = QFrame(self)
        bar.setStyleSheet("""
            QFrame {
                background-color: #F2F7FF;
                border: 1px solid #AFCDF3;
                border-radius: 8px;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                color: #172B4D;
                border-radius: 4px;
                min-width: 26px;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #C8DFFF;
            }
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        # Undo
        btn_undo = QPushButton(bar)
        btn_undo.setIcon(ui_icons.get_tool_icon("undo", color="#172B4D", size=16))
        btn_undo.setToolTip("Undo last action (Ctrl+Z)")
        btn_undo.clicked.connect(self.main_win._on_undo_requested)
        layout.addWidget(btn_undo)

        # Redo
        btn_redo = QPushButton(bar)
        btn_redo.setIcon(ui_icons.get_tool_icon("redo", color="#172B4D", size=16))
        btn_redo.setToolTip("Redo action (Ctrl+Y)")
        btn_redo.clicked.connect(self.main_win._on_redo_requested)
        layout.addWidget(btn_redo)

        bar.adjustSize()
        return bar

    def _on_zoom_changed(self, pct: int) -> None:
        self.zoom_lbl.setText(f"{pct}%")

    def _on_fit_screen_clicked(self) -> None:
        vp = self.scroll_area.viewport()
        self.canvas.fit_to_screen(vp.width(), vp.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        h = self.height()
        w = self.width()
        bar_h = 36
        y = max(10, h - bar_h - 16)

        # Anchor zoom controls at bottom-left
        self.zoom_bar.move(18, y)

        # Anchor undo/redo/delete controls at bottom-right
        act_w = self.action_bar.sizeHint().width()
        self.action_bar.move(max(10, w - act_w - 18), y)


class MainWindow(QMainWindow):
    leave_session_signal = Signal()

    def __init__(
        self,
        local_state: LocalState,
        network_client: NetworkClient,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.state = local_state
        self.network = network_client
        self.incoming_file_mgr = IncomingFileManager()

        self.setWindowTitle(f"LAN Collaborative Whiteboard - Room: {self.state.current_room_id or 'Unknown'}")
        self.resize(1400, 900)
        self.setMinimumSize(960, 640)

        # Coordinated modern light blue & white theme with soft blue scrollbars
        self.setStyleSheet("""
            QMainWindow {
                background-color: #EAF3FF;
            }
            QScrollBar:vertical {
                border: none;
                background: #EAF3FF;
                width: 10px;
                margin: 0;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #75A7FF;
                min-height: 24px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3478F6;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                border: none;
                background: #EAF3FF;
                height: 10px;
                margin: 0;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal {
                background: #75A7FF;
                min-width: 24px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #3478F6;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                background: none;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

        self._setup_ui()
        self._wire_signals()

        # Ensure Host-only actions visibility matches initial host status
        self.end_meeting_btn.setVisible(bool(self.state.is_host))
        self.toolbar.set_is_host(bool(self.state.is_host))

        # Global shortcuts for Undo and Redo
        self._undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self._undo_shortcut.activated.connect(self._on_undo_requested)
        self._redo_shortcut = QShortcut(QKeySequence.StandardKey.Redo, self)
        self._redo_shortcut.activated.connect(self._on_redo_requested)
        self._redo_shortcut_alt = QShortcut(QKeySequence("Ctrl+Y"), self)
        self._redo_shortcut_alt.activated.connect(self._on_redo_requested)

        # Global delete shortcuts for canvas selected object
        self._del_shortcut = QShortcut(QKeySequence.StandardKey.Delete, self)
        self._del_shortcut.activated.connect(self.canvas.delete_selected)
        self._backspace_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        self._backspace_shortcut.activated.connect(self.canvas.delete_selected)

    def _setup_ui(self) -> None:
        central_widget = QWidget(self)
        central_widget.setObjectName("centralWidget")
        central_widget.setStyleSheet("""
            #centralWidget {
                background-color: #EAF3FF;
                border: none;
            }
        """)
        self.setCentralWidget(central_widget)

        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(10, 10, 10, 10)
        central_layout.setSpacing(10)

        # 1. Top Header Bar
        header = self._create_header_bar()
        central_layout.addWidget(header)

        # 2. Main Content Splitter (Canvas & Toolbar on left, Sidebar on right)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.main_splitter.setStyleSheet("QSplitter::handle { background-color: #EAF3FF; width: 6px; }")

        # Left Container: Dynamic Toolbar on top + Canvas Viewport
        left_container = QWidget(self)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(10)

        # Toolbar
        self.toolbar = WhiteboardToolbar(self.state, self)
        left_layout.addWidget(self.toolbar)

        # Canvas with Viewport Container & Floating Overlays
        self.canvas = WhiteboardCanvas(self.state, self)
        self.canvas_viewport = CanvasViewportContainer(self.canvas, self, self)
        left_layout.addWidget(self.canvas_viewport, 1)

        self.main_splitter.addWidget(left_container)

        # Right Container: Sidebar with Participants and Group Chat
        self.right_container = QWidget(self)
        self.right_container.setMinimumWidth(260)
        self.right_container.setMaximumWidth(420)
        self.right_container.setStyleSheet("background-color: transparent;")
        right_layout = QVBoxLayout(self.right_container)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(10)

        self.right_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.right_splitter.setStyleSheet("QSplitter::handle { background-color: #EAF3FF; height: 6px; }")

        self.participant_panel = ParticipantPanel(self)
        self.participant_panel.set_current_user_id(self.state.user_id)
        self.right_splitter.addWidget(self.participant_panel)

        self.chat_panel = ChatPanel(self)
        self.chat_panel.set_current_username(self.state.username)
        self.right_splitter.addWidget(self.chat_panel)

        self.right_splitter.setSizes([260, 480])
        right_layout.addWidget(self.right_splitter)

        self.main_splitter.addWidget(self.right_container)
        self.main_splitter.setSizes([1060, 320])

        central_layout.addWidget(self.main_splitter, 1)

    def _create_header_bar(self) -> QFrame:
        header = QFrame(self)
        header.setFixedHeight(56)
        header.setStyleSheet("""
            QFrame {
                background-color: #DCEBFF;
                border: 1.5px solid #AFCDF3;
                border-radius: 12px;
            }
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 0, 14, 0)
        h_layout.setSpacing(12)

        # App Icon
        icon_lbl = QLabel(header)
        icon_lbl.setPixmap(ui_icons.get_app_icon(32).pixmap(32, 32))
        h_layout.addWidget(icon_lbl)

        # Brand Title
        brand_lbl = QLabel("Collaborative Whiteboard", header)
        brand_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #172B4D;")
        h_layout.addWidget(brand_lbl)

        # Room Selector / Badge Pill
        self.room_btn = QPushButton(f"Room: {self.state.current_room_id or 'room-1'} ▾", header)
        self.room_btn.setStyleSheet("""
            QPushButton {
                background-color: #F2F7FF;
                border: 1px solid #AFCDF3;
                color: #172B4D;
                font-size: 12px;
                font-weight: 600;
                padding: 5px 12px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #C8DFFF;
                border-color: #3478F6;
                color: #172B4D;
            }
        """)
        self.room_btn.setToolTip("View Room Details and LAN Information")
        self.room_btn.clicked.connect(self._show_room_info_dialog)
        h_layout.addWidget(self.room_btn)

        h_layout.addStretch()

        # Connection Status Indicator
        self.status_indicator = QLabel("● Connected", header)
        self.status_indicator.setStyleSheet("color: #16A878; font-size: 12px; font-weight: bold;")
        h_layout.addWidget(self.status_indicator)

        # User Badge with Initial Avatar
        user_name = self.state.username or "Engineer"
        initial = (user_name[:1] if user_name else "U").upper()

        self.user_badge = QFrame(header)
        self.user_badge.setStyleSheet("""
            QFrame {
                background-color: #F2F7FF;
                border: 1px solid #AFCDF3;
                border-radius: 8px;
            }
        """)
        ub_layout = QHBoxLayout(self.user_badge)
        ub_layout.setContentsMargins(6, 4, 10, 4)
        ub_layout.setSpacing(6)

        self.user_avatar = QLabel(initial, self.user_badge)
        self.user_avatar.setFixedSize(22, 22)
        self.user_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.user_avatar.setStyleSheet("""
            background-color: #3478F6;
            color: #FFFFFF;
            font-size: 11px;
            font-weight: bold;
            border-radius: 11px;
        """)
        ub_layout.addWidget(self.user_avatar)

        self.user_lbl = QLabel(f"User: {user_name}", self.user_badge)
        self.user_lbl.setStyleSheet("color: #172B4D; font-size: 12px; font-weight: 600; border: none;")
        ub_layout.addWidget(self.user_lbl)

        h_layout.addWidget(self.user_badge)

        # End Meeting Button (Danger Red Pill)
        self.end_meeting_btn = QPushButton("End Meeting", header)
        self.end_meeting_btn.setIcon(ui_icons.get_tool_icon("end_meeting", color="#FFFFFF", size=16))
        self.end_meeting_btn.setStyleSheet("""
            QPushButton {
                background-color: #E5484D;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #D62839;
            }
            QPushButton:pressed {
                background-color: #B51D2C;
            }
        """)
        self.end_meeting_btn.clicked.connect(self._on_end_meeting_clicked)
        h_layout.addWidget(self.end_meeting_btn)

        # Leave Button (Neutral Light Pill)
        leave_btn = QPushButton("Leave", header)
        leave_btn.setIcon(ui_icons.get_tool_icon("leave", color="#172B4D", size=16))
        leave_btn.setStyleSheet("""
            QPushButton {
                background-color: #F2F7FF;
                border: 1px solid #AFCDF3;
                color: #172B4D;
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #C8DFFF;
                border-color: #3478F6;
                color: #172B4D;
            }
        """)
        leave_btn.clicked.connect(self._on_leave_clicked)
        h_layout.addWidget(leave_btn)

        return header

    def _wire_signals(self) -> None:
        # Canvas -> Network
        self.canvas.operation_completed_signal.connect(self._on_local_draw_completed)
        self.canvas.object_modified_signal.connect(self._on_local_object_modified)
        self.canvas.object_deleted_signal.connect(self._on_local_object_deleted)
        self.canvas.laser_stroke_signal.connect(self._on_local_laser_stroke)
        self.canvas.laser_pointer_signal.connect(self._on_local_laser_pointer)

        # Toolbar Actions -> Network / Canvas / Dialogs
        self.toolbar.undo_requested.connect(self._on_undo_requested)
        self.toolbar.redo_requested.connect(self._on_redo_requested)
        self.toolbar.clear_requested.connect(self._on_clear_requested)
        self.toolbar.export_requested.connect(self._on_export_requested)
        self.toolbar.history_requested.connect(self._open_history_panel)
        self.toolbar.file_share_requested.connect(self._open_file_share_dialog)

        # Side Panels
        self.participant_panel.invite_requested.connect(self._show_room_info_dialog)
        self.chat_panel.send_message_requested.connect(self._on_send_chat)

        # Network -> Canvas / State / UI
        self.network.state_update_signal.connect(self._on_remote_state_update)
        self.network.canvas_snapshot_signal.connect(self._on_remote_canvas_snapshot)
        self.network.clear_canvas_signal.connect(self._on_remote_clear_canvas)
        self.network.op_ack_signal.connect(self._on_delivery_ack)
        self.network.laser_stroke_signal.connect(self._on_remote_laser_stroke)
        self.network.laser_pointer_signal.connect(self._on_remote_laser_pointer)
        self.network.file_start_signal.connect(self._on_remote_file_start)
        self.network.file_chunk_signal.connect(self._on_remote_file_chunk)
        self.network.file_complete_signal.connect(self._on_remote_file_complete)
        self.network.meeting_ended_signal.connect(self._on_remote_meeting_ended)
        self.network.participant_joined_signal.connect(self._on_remote_participant_joined)
        self.network.participant_left_signal.connect(self._on_remote_participant_left)
        self.network.chat_message_signal.connect(self._on_remote_chat_message)
        self.network.disconnected_signal.connect(self._on_remote_disconnected)
        self.network.error_signal.connect(self._on_remote_error)

    def update_session_info(
        self,
        room_id: str,
        room_name: str,
        username: str,
        participants: list,
        snapshot: dict,
        is_host: Optional[bool] = None,
    ) -> None:
        """Called when room is created or joined successfully."""
        self.state.current_room_id = room_id
        self.state.current_room_name = room_name
        self.state.username = username
        if is_host is not None:
            self.state.is_host = is_host
        self.end_meeting_btn.setVisible(bool(self.state.is_host))
        self.toolbar.set_is_host(bool(self.state.is_host))
        self.setWindowTitle(f"LAN Collaborative Whiteboard - Room: {room_id}")

        self.room_btn.setText(f"Room: {room_id} ▾")
        self.user_lbl.setText(f"User: {username}")
        initial = (username[:1] if username else "U").upper()
        self.user_avatar.setText(initial)

        self.status_indicator.setText("● Connected")
        self.status_indicator.setStyleSheet("color: #20D6A0; font-size: 12px; font-weight: bold;")

        self.participant_panel.set_current_user_id(self.state.user_id)
        self.participant_panel.update_participants(participants)
        self.chat_panel.set_current_username(username)

        # Load canvas snapshot operations
        ops = snapshot.get("operations", [])
        self.state.operations = ops
        self.state.latest_seq_num = snapshot.get("seq_num", 0)
        self.canvas.update()

    def _show_room_info_dialog(self) -> None:
        """Displays room info for inviting colleagues on LAN."""
        room_id = self.state.current_room_id or "room-1"
        info = (
            f"LAN Collaborative Whiteboard Room Details\n\n"
            f"Room ID: {room_id}\n"
            f"Port: 8555\n\n"
            f"Other computers on your Local Area Network (LAN) can connect\n"
            f"to your server IP using this Room ID to collaborate in real-time."
        )
        QMessageBox.information(self, "Room & Invite Information", info)

    # -------------------------------------------------------------------------
    # Local User Action Handlers
    # -------------------------------------------------------------------------

    def _on_local_draw_completed(self, op_type: str, data: Dict[str, Any], op_id: str) -> None:
        if not self.state.current_room_id:
            return
        self.state.pending_ops[op_id] = {"op_type": op_type, "data": data, "timestamp": time.time()}
        self.network.send_draw_operation(
            room_id=self.state.current_room_id,
            user_id=self.state.user_id,
            op_type=op_type,
            data=data,
            op_id=op_id,
        )

    def _on_local_object_modified(self, op_id: str, new_data: Dict[str, Any]) -> None:
        if not self.state.current_room_id:
            return
        self.network.send_modify_object(
            room_id=self.state.current_room_id,
            user_id=self.state.user_id,
            op_id=op_id,
            new_data=new_data,
        )

    def _on_local_object_deleted(self, op_id: str) -> None:
        if not self.state.current_room_id:
            return
        self.network.send_delete_object(
            room_id=self.state.current_room_id,
            user_id=self.state.user_id,
            op_id=op_id,
        )

    def _on_local_laser_stroke(self, points: list, color: str) -> None:
        if self.state.current_room_id:
            self.network.send_laser_stroke(self.state.current_room_id, self.state.user_id, points, color)

    def _on_local_laser_pointer(self, x: float, y: float, active: bool) -> None:
        if self.state.current_room_id:
            self.network.send_laser_pointer(self.state.current_room_id, self.state.user_id, x, y, active)

    def _on_undo_requested(self) -> None:
        sender = self.sender()
        if sender in (getattr(self, "_undo_shortcut", None), getattr(self, "_redo_shortcut", None), getattr(self, "_redo_shortcut_y", None)):
            focused = QApplication.focusWidget()
            from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
            if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
                return
        # If user has an active ephemeral laser stroke, remove the latest one locally
        if self.state.laser_strokes:
            for i in range(len(self.state.laser_strokes) - 1, -1, -1):
                if self.state.laser_strokes[i].get("user_id") == self.state.user_id:
                    self.state.laser_strokes.pop(i)
                    self.canvas.update()
                    break
        if self.state.current_room_id:
            self.network.send_undo(self.state.current_room_id, self.state.user_id)

    def _on_redo_requested(self) -> None:
        sender = self.sender()
        if sender in (getattr(self, "_undo_shortcut", None), getattr(self, "_redo_shortcut", None), getattr(self, "_redo_shortcut_y", None)):
            focused = QApplication.focusWidget()
            from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
            if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
                return
        if self.state.current_room_id:
            self.network.send_redo(self.state.current_room_id, self.state.user_id)

    def _on_clear_requested(self) -> None:
        if not self.state.is_host:
            QMessageBox.warning(self, "Permission Denied", "Only the meeting host can clear the canvas.")
            return
        if self.state.current_room_id:
            self.network.send_clear_canvas(self.state.current_room_id, self.state.user_id)

    def _on_export_requested(self) -> None:
        default_name = f"whiteboard-{self.state.current_room_id or 'export'}.png"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Whiteboard Image",
            str(Path.home() / default_name),
            "PNG Images (*.png)",
        )
        if path:
            success = self.canvas.export_to_png(path)
            if success:
                QMessageBox.information(self, "Export Successful", f"Saved whiteboard snapshot to:\n{path}")
            else:
                QMessageBox.critical(self, "Export Failed", "Could not save the image file.")

    def _open_history_panel(self) -> None:
        panel = HistoryReplayPanel(self.state, self)
        panel.timeline_scrubbed.connect(lambda idx: self.canvas.update())
        panel.restore_requested.connect(self._on_restore_historical_state)
        panel.exec()
        self.state.is_in_history_mode = False
        self.canvas.update()

    def _on_restore_historical_state(self, target_seq: int) -> None:
        if self.state.current_room_id:
            self.network.send_restore_state(self.state.current_room_id, self.state.user_id, target_seq)

    def _open_file_share_dialog(self) -> None:
        dialog = FileShareDialog(self.state, self.network, self)
        dialog.exec()

    def _on_send_chat(self, text: str) -> None:
        if self.state.current_room_id:
            self.network.send_chat(self.state.current_room_id, self.state.user_id, text)

    def _on_end_meeting_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "End Meeting",
            "Are you sure you want to officially end this meeting session?\n\n"
            "This will archive whiteboard state and generate the Session Audit Report for all participants.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.state.current_room_id:
                self.network.send_end_meeting(self.state.current_room_id, self.state.user_id)

    # -------------------------------------------------------------------------
    # Remote Network Message Receivers
    # -------------------------------------------------------------------------

    def _on_delivery_ack(self, msg: Dict[str, Any]) -> None:
        op_id = msg.get("op_id")
        if op_id:
            self.state.pending_ops.pop(op_id, None)
            self.state.acknowledged_op_ids.add(op_id)

    def _on_remote_state_update(self, msg: Dict[str, Any]) -> None:
        action = msg.get("action")
        seq = msg.get("seq_num", 0)
        self.state.latest_seq_num = seq

        if action == "draw":
            op = msg.get("operation")
            if op:
                self.state.add_operation(op)
                self.canvas.update()

        elif action == "modify":
            op = msg.get("operation")
            if op:
                self.state.modify_operation(op.get("op_id"), op.get("data", {}))
                self.canvas.update()

        elif action == "delete":
            op_id = msg.get("op_id")
            if op_id:
                self.state.delete_operation(op_id)
                self.canvas.update()

        elif action == "restore":
            ops = msg.get("operations", [])
            self.state.operations = ops
            self.canvas.update()
            self.chat_panel.add_system_message(f"Whiteboard was restored to sequence #{seq}")

        elif action == "undo":
            op_id = msg.get("op_id")
            op = msg.get("operation")
            if op_id:
                if self.state.selected_op_id == op_id:
                    self.state.selected_op_id = None
                self.state.undo_operation(op_id, op)
                self.canvas.update()

        elif action == "redo":
            op_id = msg.get("op_id")
            op = msg.get("operation")
            if op_id:
                if self.state.selected_op_id == op_id and op and op.get("is_deleted", False):
                    self.state.selected_op_id = None
                self.state.redo_operation(op_id, op)
                self.canvas.update()

    def _on_remote_laser_stroke(self, msg: Dict[str, Any]) -> None:
        pts = msg.get("points", [])
        col = msg.get("color", "#EF4444")
        uid = msg.get("user_id", "")
        if pts:
            self.state.add_laser_stroke(uid, pts, col)
            self.canvas.update()

    def _on_remote_laser_pointer(self, msg: Dict[str, Any]) -> None:
        sender_id = msg.get("sender_id")
        if sender_id:
            self.state.laser_pointers[sender_id] = {
                "x": msg.get("x", 0),
                "y": msg.get("y", 0),
                "username": msg.get("sender_name", "Participant"),
                "timestamp": time.time(),
                "active": msg.get("active", True),
            }
            self.canvas.update()

    def _on_remote_file_start(self, msg: Dict[str, Any]) -> None:
        self.incoming_file_mgr.handle_file_start(msg)
        sender = msg.get("sender_name", "A user")
        filename = msg.get("filename", "file")
        self.chat_panel.add_system_message(f"Incoming file '{filename}' from {sender}...")

    def _on_remote_file_chunk(self, msg: Dict[str, Any]) -> None:
        self.incoming_file_mgr.handle_file_chunk(msg)

    def _on_remote_file_complete(self, msg: Dict[str, Any]) -> None:
        result = self.incoming_file_mgr.handle_file_complete(msg)
        if result:
            filename, file_bytes = result
            reply = QMessageBox.question(
                self,
                "Save Received File",
                f"File '{filename}' ({len(file_bytes) / 1024:.1f} KB) was received successfully.\n"
                f"Would you like to save it to your computer?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                save_path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save Received File",
                    str(Path.home() / filename),
                )
                if save_path:
                    try:
                        with open(save_path, "wb") as f:
                            f.write(file_bytes)
                        QMessageBox.information(self, "Saved", f"File saved to {save_path}")
                    except Exception as e:
                        QMessageBox.critical(self, "Save Error", f"Failed to save file: {e}")

    def _on_remote_meeting_ended(self, msg: Dict[str, Any]) -> None:
        host = msg.get("host_name", "Host")
        report_file = msg.get("report_file", "")
        QMessageBox.information(
            self,
            "Meeting Concluded",
            f"The host ({host}) has concluded this meeting session.\n\n"
            f"Session Report saved to:\n{report_file}\n\n"
            "Returning to session launcher.",
        )
        self.network.disconnect_from_server("Meeting ended by host")
        self.state.reset_room_state()
        self.leave_session_signal.emit()

    def _on_remote_canvas_snapshot(self, msg: Dict[str, Any]) -> None:
        snapshot = msg.get("snapshot", {})
        self.state.operations = snapshot.get("operations", [])
        self.state.latest_seq_num = snapshot.get("seq_num", 0)
        self.canvas.update()

    def _on_remote_clear_canvas(self, msg: Dict[str, Any]) -> None:
        self.state.clear_operations()
        self.canvas.update()
        username = msg.get("username", "Host")
        self.chat_panel.add_system_message(f"Whiteboard was cleared by host {username}")

    def _on_remote_participant_joined(self, msg: Dict[str, Any]) -> None:
        self.participant_panel.add_participant(msg)
        username = msg.get("username", "Someone")
        self.chat_panel.add_system_message(f"{username} joined the session")

    def _on_remote_participant_left(self, msg: Dict[str, Any]) -> None:
        user_id = msg.get("user_id")
        username = msg.get("username", "Someone")
        if user_id:
            self.participant_panel.remove_participant(user_id)
        self.chat_panel.add_system_message(f"{username} left the session")

    def _on_remote_chat_message(self, msg: Dict[str, Any]) -> None:
        sender_id = msg.get("user_id")
        username = msg.get("username", "Unknown")
        text = msg.get("text", "")
        ts = msg.get("timestamp")
        is_self = (sender_id == self.state.user_id)
        msg_id = msg.get("message_id")
        self.chat_panel.add_chat_message(username, text, ts, is_self=is_self, message_id=msg_id)

    def _on_remote_disconnected(self, reason: str) -> None:
        self.status_indicator.setText("● Disconnected")
        self.status_indicator.setStyleSheet("color: #EF4444; font-size: 12px; font-weight: bold;")
        self.chat_panel.add_system_message(f"Disconnected from server: {reason}")

    def _on_remote_error(self, message: str) -> None:
        self.chat_panel.add_system_message(f"Server notification: {message}")

    def _on_leave_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "Leave Session",
            "Are you sure you want to leave this whiteboard session?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.state.current_room_id:
                self.network.leave_room(self.state.current_room_id, self.state.user_id)
            self.network.disconnect_from_server("User left session")
            self.state.reset_room_state()
            self.leave_session_signal.emit()
