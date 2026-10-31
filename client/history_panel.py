"""
Whiteboard History and Replay Panel for Collaborative Whiteboard.
Allows participants to review ordered operation history, scrub the timeline,
replay creation step-by-step with adjustable playback speed, and restore historical states.
"""

import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from common.constants import REPLAY_SPEEDS
from client.local_state import LocalState


class HistoryReplayPanel(QDialog):
    # Signal to request server to rollback / restore state to a historical sequence
    restore_requested = Signal(int)
    # Signal emitted when scrubbing the preview
    timeline_scrubbed = Signal(int)

    def __init__(self, local_state: LocalState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = local_state
        self.setWindowTitle("Whiteboard History and Playback")
        self.resize(520, 600)
        self.setMinimumSize(420, 480)

        self._is_playing = False
        self._current_index = 0
        self._replay_timer = QTimer(self)
        self._replay_timer.timeout.connect(self._on_replay_tick)

        self._setup_ui()
        self._load_operations()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header Title
        title_label = QLabel("Whiteboard Operation History", self)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #0F172A;")
        layout.addWidget(title_label)

        sub_label = QLabel("Browse timeline, replay drawing steps, or restore a previous state.", self)
        sub_label.setStyleSheet("font-size: 12px; color: #64748B;")
        layout.addWidget(sub_label)

        # Operations List View
        self.list_widget = QListWidget(self)
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                background-color: #F8FAFC;
                padding: 6px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #E2E8F0;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #EFF6FF;
                color: #1D4ED8;
                border: 1px solid #93C5FD;
            }
        """)
        self.list_widget.currentRowChanged.connect(self._on_list_row_selected)
        layout.addWidget(self.list_widget, 1)

        # Timeline Scrubber Slider
        timeline_layout = QVBoxLayout()
        timeline_layout.setSpacing(4)

        slider_header = QHBoxLayout()
        self.timeline_label = QLabel("Timeline: 0 / 0", self)
        self.timeline_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        slider_header.addWidget(self.timeline_label)

        slider_header.addStretch()
        speed_label = QLabel("Speed:", self)
        speed_label.setStyleSheet("font-size: 12px; color: #64748B;")
        slider_header.addWidget(speed_label)

        self.speed_combo = QComboBox(self)
        for s in REPLAY_SPEEDS:
            self.speed_combo.addItem(f"{s}x", s)
        self.speed_combo.setCurrentIndex(1)  # 1.0x default
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        slider_header.addWidget(self.speed_combo)

        timeline_layout.addLayout(slider_header)

        self.timeline_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.valueChanged.connect(self._on_slider_moved)
        timeline_layout.addWidget(self.timeline_slider)
        layout.addLayout(timeline_layout)

        # Playback Controls Bar (Step Back, Play/Pause, Step Forward)
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        self.btn_step_back = QPushButton("<< Step Back", self)
        self.btn_step_back.clicked.connect(self._step_backward)
        controls_layout.addWidget(self.btn_step_back)

        self.btn_play_pause = QPushButton("Play Replay", self)
        self.btn_play_pause.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.btn_play_pause.clicked.connect(self._toggle_playback)
        controls_layout.addWidget(self.btn_play_pause)

        self.btn_step_fwd = QPushButton("Step Next >>", self)
        self.btn_step_fwd.clicked.connect(self._step_forward)
        controls_layout.addWidget(self.btn_step_fwd)

        layout.addLayout(controls_layout)

        # Restore and Close Action Buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.btn_restore = QPushButton("Restore Canvas to this State", self)
        self.btn_restore.setStyleSheet("""
            QPushButton {
                background-color: #F59E0B;
                color: #FFFFFF;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #D97706;
            }
        """)
        self.btn_restore.clicked.connect(self._on_restore_clicked)
        actions_layout.addWidget(self.btn_restore)

        actions_layout.addStretch()

        self.btn_close = QPushButton("Return to Live Whiteboard", self)
        self.btn_close.clicked.connect(self.close)
        actions_layout.addWidget(self.btn_close)

        layout.addLayout(actions_layout)

    def _load_operations(self) -> None:
        self.list_widget.clear()
        ops = self.state.operations

        for idx, op in enumerate(ops):
            seq = op.get("seq_num", idx + 1)
            op_type = op.get("op_type", "draw")
            author = op.get("author_name") or op.get("username", "Unknown")
            ts = op.get("created_at", 0)
            time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else ""

            item_text = f"#{seq} | {op_type.upper():<8} by {author:<12} [{time_str}]"
            item = QListWidgetItem(item_text)
            self.list_widget.addItem(item)

        total_ops = len(ops)
        if total_ops > 0:
            self.timeline_slider.setRange(0, total_ops - 1)
            self.timeline_slider.setValue(total_ops - 1)
            self._current_index = total_ops - 1
            self.timeline_label.setText(f"Timeline: {total_ops} / {total_ops}")
        else:
            self.timeline_slider.setRange(0, 0)
            self.timeline_label.setText("Timeline: 0 / 0")

    def _on_speed_changed(self) -> None:
        if self._is_playing:
            speed = self.speed_combo.currentData() or 1.0
            interval_ms = int(1000 / speed)
            self._replay_timer.setInterval(interval_ms)

    def _toggle_playback(self) -> None:
        if self._is_playing:
            self._pause_playback()
        else:
            self._start_playback()

    def _start_playback(self) -> None:
        if not self.state.operations:
            return

        self._is_playing = True
        self.btn_play_pause.setText("Pause")
        self.state.is_in_history_mode = True

        if self._current_index >= len(self.state.operations) - 1:
            self._current_index = 0
            self.timeline_slider.setValue(0)

        speed = self.speed_combo.currentData() or 1.0
        interval_ms = int(1000 / speed)
        self._replay_timer.start(interval_ms)

    def _pause_playback(self) -> None:
        self._is_playing = False
        self.btn_play_pause.setText("Play Replay")
        self._replay_timer.stop()

    def _on_replay_tick(self) -> None:
        if self._current_index < len(self.state.operations) - 1:
            self._current_index += 1
            self.timeline_slider.setValue(self._current_index)
        else:
            self._pause_playback()

    def _step_forward(self) -> None:
        self._pause_playback()
        if self._current_index < len(self.state.operations) - 1:
            self._current_index += 1
            self.timeline_slider.setValue(self._current_index)

    def _step_backward(self) -> None:
        self._pause_playback()
        if self._current_index > 0:
            self._current_index -= 1
            self.timeline_slider.setValue(self._current_index)

    def _on_slider_moved(self, val: int) -> None:
        self._current_index = val
        total = len(self.state.operations)
        self.timeline_label.setText(f"Timeline: {val + 1} / {total}")
        self.list_widget.setCurrentRow(val)

        # Put canvas into history preview mode up to this index
        self.state.is_in_history_mode = True
        self.state.history_view_index = val
        self.timeline_scrubbed.emit(val)

    def _on_list_row_selected(self, row: int) -> None:
        if row >= 0 and row != self._current_index:
            self.timeline_slider.setValue(row)

    def _on_restore_clicked(self) -> None:
        if not self.state.operations:
            return

        target_op = self.state.operations[self._current_index]
        target_seq = target_op.get("seq_num", self._current_index + 1)

        reply = QMessageBox.question(
            self,
            "Restore Historical State",
            f"Are you sure you want to restore the shared whiteboard back to Sequence #{target_seq}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._pause_playback()
            self.state.is_in_history_mode = False
            self.restore_requested.emit(target_seq)
            self.close()

    def closeEvent(self, event) -> None:
        self._pause_playback()
        self.state.is_in_history_mode = False
        super().closeEvent(event)
