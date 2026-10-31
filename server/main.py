"""
Server Application Entry Point for LAN-Based Collaborative Whiteboard.
Handles command-line arguments, signal handling, and clean server startup.
"""

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.constants import DEFAULT_HOST, DEFAULT_PORT
from server.server_config import ServerConfig
from server.socket_server import SocketServer


def setup_logging(verbose: bool = False) -> None:
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def print_banner(host: str, port: int, lan_ips: list) -> None:
    print("\n" + "=" * 65)
    print("   LAN-BASED MULTI-USER COLLABORATIVE WHITEBOARD SERVER")
    print("=" * 65)
    print(f" Listening Address : {host}:{port}")
    print(f" Available LAN IPs : {', '.join(lan_ips)}")
    print(" Architecture      : Centralized TCP Socket Server")
    print(" Status            : Online & Ready for Client Connections")
    print("=" * 65)
    print(" NOTE: Other computers on your LAN should connect to one of")
    print(f" the LAN IPs above using port {port}.\n")
    print(" Press Ctrl+C in this terminal to stop the server gracefully.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collaborative Whiteboard TCP Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host address to bind (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port number to bind (default: {DEFAULT_PORT})")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    config = ServerConfig(host=args.host, port=args.port)
    lan_ips = config.get_local_lan_ips()
    print_banner(args.host, args.port, lan_ips)

    server = SocketServer(config)

    def handle_sigint(sig, frame):
        print("\n[Shutdown] Received interrupt signal. Stopping server...")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_sigint)

    try:
        server.start()
        # Keep main thread alive
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        handle_sigint(None, None)
    except Exception as e:
        logging.critical("Fatal server error: %s", e, exc_info=True)
        server.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
