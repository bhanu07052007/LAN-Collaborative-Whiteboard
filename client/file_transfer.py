"""
File Transfer Manager and Dialog for Collaborative Whiteboard.
Handles chunked binary file sharing over TCP with base64 streaming,
progress tracking, validation, and local saving for recipients.
"""

import base64
import math
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from common.constants import ALLOWED_FILE_EXTENSIONS, FILE_CHUNK_SIZE, MAX_FILE_SIZE
from client.local_state import LocalState
from client.network_client import NetworkClient


class FileSenderThread(QThread):
    progress_signal = Signal(int, int)  # current_chunk, total_chunks
    completed_signal = Signal(str, str) # file_id, filename
    failed_signal = Signal(str)         # error_message

    def __init__(
        self,
        file_path: str,
        room_id: str,
        user_id: str,
        network_client: NetworkClient,
    ) -> None:
        super().__init__()
        self.file_path = file_path
        self.room_id = room_id
        self.user_id = user_id
        self.network = network_client
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        try:
            path = Path(self.file_path)
            file_size = path.stat().st_size
            filename = path.name

            if file_size > MAX_FILE_SIZE:
                self.failed_signal.emit(f"File size {file_size / (1024 * 1024):.1f} MB exceeds limit ({MAX_FILE_SIZE / (1024 * 1024):.1f} MB)")
                return

            total_chunks = max(1, math.ceil(file_size / FILE_CHUNK_SIZE))
            file_id = f"file-{uuid.uuid4().hex[:10]}"

            # 1. Send FILE_START
            self.network.send_file_start(self.room_id, self.user_id, file_id, filename, file_size)

            # 2. Read and transmit chunks
            with open(path, "rb") as f:
                for chunk_idx in range(total_chunks):
                    if self._is_cancelled:
                        return
                    raw_chunk = f.read(FILE_CHUNK_SIZE)
                    if not raw_chunk:
                        break
                    b64_data = base64.b64encode(raw_chunk).decode("ascii")
                    self.network.send_file_chunk(
                        room_id=self.room_id,
                        user_id=self.user_id,
                        file_id=file_id,
                        chunk_index=chunk_idx,
                        total_chunks=total_chunks,
                        data_base64=b64_data,
                    )
                    self.progress_signal.emit(chunk_idx + 1, total_chunks)

            # 3. Send FILE_COMPLETE
            self.network.send_file_complete(self.room_id, self.user_id, file_id)
            self.completed_signal.emit(file_id, filename)

        except Exception as e:
            self.failed_signal.emit(f"Error transferring file: {e}")


class FileShareDialog(QDialog):
    """Dialog for initiating file upload and tracking progress."""

    def __init__(
        self,
        local_state: LocalState,
        network_client: NetworkClient,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.state = local_state
        self.network = network_client
        self.setWindowTitle("Share File Over TCP")
        self.resize(460, 220)
        self.setMinimumSize(400, 200)

        self.selected_file_path: Optional[str] = None
        self._sender_thread: Optional[FileSenderThread] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Share File with Room Participants", self)
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #0F172A;")
        layout.addWidget(title)

        # File selection row
        file_row = QHBoxLayout()
        self.path_label = QLabel("No file selected", self)
        self.path_label.setStyleSheet("border: 1px solid #CBD5E1; border-radius: 6px; padding: 6px; background-color: #F8FAFC;")
        file_row.addWidget(self.path_label, 1)

        browse_btn = QPushButton("Browse...", self)
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        # Progress Bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #2563EB;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready to upload", self)
        self.status_label.setStyleSheet("font-size: 12px; color: #64748B;")
        layout.addWidget(self.status_label)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.send_btn = QPushButton("Start Transfer", self)
        self.send_btn.setEnabled(False)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
            QPushButton:disabled {
                background-color: #94A3B8;
            }
        """)
        self.send_btn.clicked.connect(self._start_transfer)
        btn_layout.addWidget(self.send_btn)

        self.close_btn = QPushButton("Cancel", self)
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File to Share",
            "",
            "Allowed Files (*.png *.jpg *.jpeg *.pdf *.txt *.json *.csv *.md *.py *.zip);;All Files (*.*)",
        )
        if file_path:
            self.selected_file_path = file_path
            path_obj = Path(file_path)
            size_mb = path_obj.stat().st_size / (1024 * 1024)
            self.path_label.setText(f"{path_obj.name} ({size_mb:.2f} MB)")
            self.send_btn.setEnabled(True)

    def _start_transfer(self) -> None:
        if not self.selected_file_path or not self.state.current_room_id:
            return

        self.send_btn.setEnabled(False)
        self.status_label.setText("Transferring chunks over TCP...")

        self._sender_thread = FileSenderThread(
            file_path=self.selected_file_path,
            room_id=self.state.current_room_id,
            user_id=self.state.user_id,
            network_client=self.network,
        )
        self._sender_thread.progress_signal.connect(self._on_progress)
        self._sender_thread.completed_signal.connect(self._on_completed)
        self._sender_thread.failed_signal.connect(self._on_failed)
        self._sender_thread.start()

    def _on_progress(self, current: int, total: int) -> None:
        pct = int((current / total) * 100)
        self.progress_bar.setValue(pct)
        self.status_label.setText(f"Sending chunk {current} of {total} ({pct}%)...")

    def _on_completed(self, file_id: str, filename: str) -> None:
        self.status_label.setText(f"File '{filename}' shared successfully!")
        QMessageBox.information(self, "Transfer Complete", f"Successfully shared '{filename}' with the room!")
        self.accept()

    def _on_failed(self, error_msg: str) -> None:
        self.status_label.setText(f"Failed: {error_msg}")
        QMessageBox.critical(self, "Transfer Error", error_msg)
        self.send_btn.setEnabled(True)

    def closeEvent(self, event) -> None:
        if self._sender_thread and self._sender_thread.isRunning():
            self._sender_thread.cancel()
            self._sender_thread.wait(500)
        super().closeEvent(event)


class IncomingFileManager:
    """Manages received TCP chunks across rooms and reassembles files."""

    def __init__(self) -> None:
        # {file_id: {"filename": str, "file_size": int, "sender_name": str, "chunks": {idx: bytes}, "total_chunks": int}}
        self._incoming: Dict[str, Dict[str, Any]] = {}

    def handle_file_start(self, msg: Dict[str, Any]) -> None:
        file_id = msg.get("file_id")
        if not file_id:
            return
        self._incoming[file_id] = {
            "file_id": file_id,
            "filename": msg.get("filename", "downloaded_file"),
            "file_size": msg.get("file_size", 0),
            "sender_name": msg.get("sender_name", "User"),
            "chunks": {},
            "total_chunks": 0,
        }

    def handle_file_chunk(self, msg: Dict[str, Any]) -> Tuple[int, int]:
        file_id = msg.get("file_id")
        if not file_id or file_id not in self._incoming:
            return 0, 0

        info = self._incoming[file_id]
        chunk_idx = msg.get("chunk_index", 0)
        total = msg.get("total_chunks", 1)
        info["total_chunks"] = total

        b64_data = msg.get("data", "")
        raw_bytes = base64.b64decode(b64_data.encode("ascii"))
        info["chunks"][chunk_idx] = raw_bytes
        return len(info["chunks"]), total

    def handle_file_complete(self, msg: Dict[str, Any]) -> Optional[Tuple[str, bytes]]:
        file_id = msg.get("file_id")
        if not file_id or file_id not in self._incoming:
            return None

        info = self._incoming.pop(file_id)
        filename = info["filename"]
        chunks = info["chunks"]

        # Reassemble chunks in order
        assembled = bytearray()
        for idx in range(info.get("total_chunks", len(chunks))):
            if idx in chunks:
                assembled.extend(chunks[idx])

        return filename, bytes(assembled)
