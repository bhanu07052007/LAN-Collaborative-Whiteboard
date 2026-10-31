"""
Server Configuration Module.
Handles settings, storage paths, and network IP discovery.
"""

import os
import socket
from pathlib import Path
from typing import List, Optional

from common.constants import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    PING_INTERVAL,
    PING_TIMEOUT,
    SOCKET_TIMEOUT,
)

# Root directory of Collaborative-Whiteboard
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
MEETING_LOGS_DIR = DATA_DIR / "meeting_logs"

# Ensure persistence directories exist
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
MEETING_LOGS_DIR.mkdir(parents=True, exist_ok=True)


class ServerConfig:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        sessions_dir: Path = SESSIONS_DIR,
        socket_timeout: float = SOCKET_TIMEOUT,
        ping_interval: float = PING_INTERVAL,
        ping_timeout: float = PING_TIMEOUT,
        meeting_logs_dir: Optional[Path] = None,
    ):
        self.host = host
        self.port = port
        self.sessions_dir = sessions_dir
        self.data_dir = self.sessions_dir.parent
        self.meeting_logs_dir = meeting_logs_dir or (self.data_dir / "meeting_logs")
        self.meeting_logs_dir.mkdir(parents=True, exist_ok=True)
        self.socket_timeout = socket_timeout
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

    @staticmethod
    def get_local_lan_ips() -> List[str]:
        """
        Discovers and returns all non-loopback IPv4 addresses
        assigned to the local machine across LAN interfaces.
        """
        ips = []
        try:
            # Method 1: Hostname lookup
            hostname = socket.gethostname()
            _, _, host_ips = socket.gethostbyname_ex(hostname)
            for ip in host_ips:
                if not ip.startswith("127.") and ip not in ips:
                    ips.append(ip)
        except Exception:
            pass

        try:
            # Method 2: UDP routing probe (does not send packets outside)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            # 10.255.255.255 is a standard RFC broadcast target
            s.connect(("10.255.255.255", 1))
            routed_ip = s.getsockname()[0]
            if routed_ip not in ips and not routed_ip.startswith("127."):
                ips.append(routed_ip)
            s.close()
        except Exception:
            pass

        if not ips:
            ips.append("127.0.0.1")

        return ips
