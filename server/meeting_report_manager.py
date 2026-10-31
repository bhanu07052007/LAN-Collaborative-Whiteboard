"""
Meeting Report Manager for LAN Collaborative Whiteboard Server.
Tracks participant sessions, join/exit timestamps, early departures, whiteboard activity,
chat messages, file transfers, and generates comprehensive audit logs in:
    data/meeting_logs/<room_id>_<YYYY-MM-DD>_session.log
"""

import datetime
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("MeetingReportManager")


@dataclass
class ParticipantSessionRecord:
    user_id: str
    username: str
    is_host: bool = False
    join_time: float = field(default_factory=time.time)
    exit_time: Optional[float] = None
    drawing_count: int = 0
    chat_count: int = 0
    file_count: int = 0
    exited_early: bool = False
    completed: bool = False


@dataclass
class SessionEvent:
    timestamp: float
    description: str


class RoomSessionTracker:
    """Tracks metrics and events for a single whiteboard room session."""

    def __init__(self, room_id: str, room_name: str, host_id: str, host_name: str, logs_dir: Path) -> None:
        self.room_id = room_id
        self.room_name = room_name
        self.host_id = host_id
        self.host_name = host_name
        self.logs_dir = logs_dir
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.termination_reason = "In Progress"

        self.participants: Dict[str, ParticipantSessionRecord] = {}
        self.events: List[SessionEvent] = []
        self._lock = threading.RLock()

        # Log initial event
        self.record_event(f"Session started for room '{room_name}' ({room_id})")
        self.record_join(host_id, host_name, is_host=True)

    def record_event(self, description: str, timestamp: Optional[float] = None) -> None:
        with self._lock:
            ts = timestamp or time.time()
            self.events.append(SessionEvent(timestamp=ts, description=description))
            logger.debug("[%s] Event: %s", self.room_id, description)

    def record_join(self, user_id: str, username: str, is_host: bool = False) -> None:
        with self._lock:
            now = time.time()
            if user_id not in self.participants:
                record = ParticipantSessionRecord(
                    user_id=user_id,
                    username=username,
                    is_host=is_host,
                    join_time=now,
                )
                self.participants[user_id] = record
            else:
                record = self.participants[user_id]
                record.exit_time = None
                record.exited_early = False
                record.completed = False

            role_str = " (Host)" if is_host else ""
            self.record_event(f"Participant {username} joined the session{role_str}", now)

    def record_leave(self, user_id: str, early_exit: bool = True) -> None:
        with self._lock:
            now = time.time()
            record = self.participants.get(user_id)
            if record:
                record.exit_time = now
                record.exited_early = early_exit
                record.completed = not early_exit
                status_str = " (Exited Early)" if early_exit else ""
                self.record_event(f"Participant {record.username} left the session{status_str}", now)

    def record_drawing(self, user_id: str, op_type: str, op_id: str, seq_num: int) -> None:
        with self._lock:
            record = self.participants.get(user_id)
            username = record.username if record else "User"
            if record:
                record.drawing_count += 1
            self.record_event(f"{username} created {op_type} object (ID: {op_id}, seq {seq_num})")

    def record_chat(self, user_id: str, text: str) -> None:
        with self._lock:
            record = self.participants.get(user_id)
            username = record.username if record else "User"
            if record:
                record.chat_count += 1
            preview = (text[:30] + "...") if len(text) > 30 else text
            self.record_event(f"{username} sent chat message: \"{preview}\"")

    def record_file_shared(self, user_id: str, filename: str, file_size: int) -> None:
        with self._lock:
            record = self.participants.get(user_id)
            username = record.username if record else "User"
            if record:
                record.file_count += 1
            size_kb = file_size / 1024.0
            self.record_event(f"{username} shared file '{filename}' ({size_kb:.1f} KB)")

    def record_clear(self, user_id: str, username: str, seq_num: int) -> None:
        with self._lock:
            self.record_event(f"Whiteboard cleared by {username} (seq {seq_num})")

    def finish_session(self, reason: str = "Host ended meeting") -> None:
        with self._lock:
            if self.end_time is not None:
                return
            self.end_time = time.time()
            self.termination_reason = reason
            self.record_event(f"Session ended: {reason}", self.end_time)

            # Mark all currently active participants as completed
            for record in self.participants.values():
                if record.exit_time is None:
                    record.exit_time = self.end_time
                    record.completed = True
                    record.exited_early = False

    def generate_report_text(self, final_op_count: int, persistence_path: Optional[str] = None) -> str:
        """Constructs formatted Section A, B, C, D report."""
        with self._lock:
            end_ts = self.end_time or time.time()
            duration_sec = max(0, int(end_ts - self.start_time))
            hours = duration_sec // 3600
            minutes = (duration_sec % 3600) // 60
            seconds = duration_sec % 60
            duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            start_dt = datetime.datetime.fromtimestamp(self.start_time)
            end_dt = datetime.datetime.fromtimestamp(end_ts)
            date_str = start_dt.strftime("%Y-%m-%d")

            lines = [
                "=" * 80,
                "LAN COLLABORATIVE WHITEBOARD - MEETING SESSION REPORT",
                "=" * 80,
                "",
                "SECTION A: SESSION INFORMATION",
                "-" * 80,
                f"Room ID             : {self.room_id}",
                f"Room Name           : {self.room_name}",
                f"Host / Creator      : {self.host_name} ({self.host_id})",
                f"Session Start Time  : {start_dt.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Session End Time    : {end_dt.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Total Duration      : {duration_str}",
                f"Total Participants  : {len(self.participants)}",
                f"Final Ops Count     : {final_op_count}",
                "",
                "SECTION B: PARTICIPANT ACTIVITY LOG",
                "-" * 80,
                f"{'Username':<15} | {'User ID':<14} | {'Join Time':<8} | {'Exit Time':<8} | {'Duration':<8} | {'Drawings':<8} | {'Chat':<5} | {'Files':<5} | {'Status'}",
                "-" * 80,
            ]

            for p in self.participants.values():
                j_str = datetime.datetime.fromtimestamp(p.join_time).strftime("%H:%M:%S")
                if p.exit_time:
                    e_str = datetime.datetime.fromtimestamp(p.exit_time).strftime("%H:%M:%S")
                    p_dur_sec = max(0, int(p.exit_time - p.join_time))
                else:
                    e_str = end_dt.strftime("%H:%M:%S")
                    p_dur_sec = max(0, int(end_ts - p.join_time))

                p_hours = p_dur_sec // 3600
                p_mins = (p_dur_sec % 3600) // 60
                p_secs = p_dur_sec % 60
                p_dur_str = f"{p_hours:02d}:{p_mins:02d}:{p_secs:02d}"

                status = "Exited Early" if p.exited_early else "Completed"
                lines.append(
                    f"{p.username:<15} | {p.user_id:<14} | {j_str:<8} | {e_str:<8} | {p_dur_str:<8} | "
                    f"{p.drawing_count:>8} | {p.chat_count:>5} | {p.file_count:>5} | {status}"
                )

            lines.extend([
                "",
                "SECTION C: CHRONOLOGICAL EVENT HISTORY",
                "-" * 80,
            ])

            for ev in self.events:
                ev_time_str = datetime.datetime.fromtimestamp(ev.timestamp).strftime("%H:%M:%S")
                lines.append(f"[{ev_time_str}] {ev.description}")

            log_filename = f"{self.room_id}_{date_str}_session.log"
            lines.extend([
                "",
                "SECTION D: SESSION END SUMMARY",
                "-" * 80,
                f"Termination Reason  : {self.termination_reason}",
                f"State Persistence   : {persistence_path or 'Saved to disk'}",
                f"Report File         : data/meeting_logs/{log_filename}",
                f"Generated At        : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 80,
                "",
            ])

            return "\n".join(lines)

    def write_report_to_disk(self, final_op_count: int, persistence_path: Optional[str] = None) -> Path:
        """Writes report to meeting_logs folder."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d")
        report_filename = f"{self.room_id}_{date_str}_session.log"
        target_path = self.logs_dir / report_filename

        text = self.generate_report_text(final_op_count, persistence_path)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(text)

        logger.info("Meeting session report written to %s", target_path)

        # Also write to secondary project root if separated
        secondary_dir = Path("data") / "meeting_logs"
        if secondary_dir.resolve() != self.logs_dir.resolve():
            try:
                secondary_dir.mkdir(parents=True, exist_ok=True)
                with open(secondary_dir / report_filename, "w", encoding="utf-8") as f:
                    f.write(text)
            except Exception:
                pass

        return target_path


class MeetingReportManager:
    """Manages session trackers across all whiteboard rooms on the server."""

    def __init__(self, logs_dir: Optional[Path] = None) -> None:
        if logs_dir is None:
            self.logs_dir = Path(__file__).resolve().parent.parent / "data" / "meeting_logs"
        else:
            self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._trackers: Dict[str, RoomSessionTracker] = {}
        self._lock = threading.RLock()

    def get_or_create_tracker(
        self,
        room_id: str,
        room_name: str,
        host_id: str,
        host_name: str,
    ) -> RoomSessionTracker:
        with self._lock:
            if room_id not in self._trackers:
                self._trackers[room_id] = RoomSessionTracker(
                    room_id=room_id,
                    room_name=room_name,
                    host_id=host_id,
                    host_name=host_name,
                    logs_dir=self.logs_dir,
                )
            return self._trackers[room_id]

    def get_tracker(self, room_id: str) -> Optional[RoomSessionTracker]:
        with self._lock:
            return self._trackers.get(room_id)

    def close_all_sessions(self, reason: str = "Server shutdown") -> List[Path]:
        """Closes all ongoing trackers and writes reports to disk."""
        generated_paths = []
        with self._lock:
            for tracker in self._trackers.values():
                if tracker.end_time is None:
                    tracker.finish_session(reason)
                    path = tracker.write_report_to_disk(final_op_count=0)
                    generated_paths.append(path)
        return generated_paths
