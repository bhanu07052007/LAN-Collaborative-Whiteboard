"""
Connection Manager for LAN Collaborative Whiteboard Server.
Maintains thread-safe registry of connected clients and manages message dispatch.
Enforces per-client send locks to prevent message interleaving over TCP sockets.
"""

import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from common.protocol import send_message

logger = logging.getLogger("ConnectionManager")


@dataclass
class ClientConnection:
    user_id: str
    username: str
    sock: socket.socket
    address: Tuple[str, int]
    room_id: Optional[str] = None
    connected_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    is_active: bool = True
    send_lock: threading.Lock = field(default_factory=threading.Lock)


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: Dict[str, ClientConnection] = {}
        self._lock = threading.RLock()

    def register_client(
        self,
        user_id: str,
        username: str,
        sock: socket.socket,
        address: Tuple[str, int],
        room_id: Optional[str] = None,
    ) -> ClientConnection:
        """Registers a new client connection in the thread-safe registry."""
        with self._lock:
            # If an existing client with this user_id exists, unregister first
            if user_id in self._clients:
                logger.warning("Client %s already registered. Overwriting old connection.", user_id)
                self.unregister_client(user_id)

            client = ClientConnection(
                user_id=user_id,
                username=username,
                sock=sock,
                address=address,
                room_id=room_id,
            )
            self._clients[user_id] = client
            logger.info("Registered client %s (%s) from %s:%s", username, user_id, address[0], address[1])
            return client

    def unregister_client(self, user_id: str) -> Optional[ClientConnection]:
        """Safely unregisters and closes a client connection."""
        with self._lock:
            client = self._clients.pop(user_id, None)
            if client is None:
                return None

            client.is_active = False
            # Safely close socket
            try:
                client.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.sock.close()
            except OSError:
                pass

            logger.info("Unregistered client %s (%s)", client.username, user_id)
            return client

    def get_client(self, user_id: str) -> Optional[ClientConnection]:
        """Retrieves a client by user ID."""
        with self._lock:
            return self._clients.get(user_id)

    def set_client_room(self, user_id: str, room_id: Optional[str]) -> bool:
        """Updates the room assigned to a client."""
        with self._lock:
            client = self._clients.get(user_id)
            if client:
                client.room_id = room_id
                return True
            return False

    def update_activity(self, user_id: str) -> None:
        """Updates the last_active timestamp for keepalive monitoring."""
        with self._lock:
            client = self._clients.get(user_id)
            if client:
                client.last_active = time.time()

    def send_to_client(self, user_id: str, message_dict: Dict[str, Any]) -> bool:
        """
        Sends a message to a specific client with guaranteed per-client lock.
        Prevents multiple threads from interleaving bytes on the TCP socket.
        """
        client: Optional[ClientConnection] = None
        with self._lock:
            client = self._clients.get(user_id)

        if not client or not client.is_active:
            return False

        with client.send_lock:
            try:
                send_message(client.sock, message_dict)
                return True
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.warning("Failed to send message to %s (%s): %s", client.username, user_id, e)
                # Unregister dead client
                self.unregister_client(user_id)
                return False

    def broadcast_to_room(
        self,
        room_id: str,
        message_dict: Dict[str, Any],
        exclude_user_id: Optional[str] = None,
    ) -> int:
        """
        Broadcasts a message to all active clients in a specific room.
        Returns the count of successful deliveries.
        """
        targets: List[ClientConnection] = []
        with self._lock:
            for client in self._clients.values():
                if client.is_active and client.room_id == room_id:
                    if exclude_user_id and client.user_id == exclude_user_id:
                        continue
                    targets.append(client)

        successful_count = 0
        for client in targets:
            with client.send_lock:
                try:
                    send_message(client.sock, message_dict)
                    successful_count += 1
                except (ConnectionResetError, BrokenPipeError, OSError) as e:
                    logger.warning("Broadcast delivery failed for %s (%s): %s", client.username, client.user_id, e)
                    self.unregister_client(client.user_id)

        return successful_count

    def broadcast_all(self, message_dict: Dict[str, Any]) -> int:
        """Broadcasts a message to every connected client."""
        targets: List[ClientConnection] = []
        with self._lock:
            targets = [c for c in self._clients.values() if c.is_active]

        count = 0
        for client in targets:
            with client.send_lock:
                try:
                    send_message(client.sock, message_dict)
                    count += 1
                except Exception:
                    self.unregister_client(client.user_id)
        return count

    def get_room_clients(self, room_id: str) -> List[ClientConnection]:
        """Returns all connected clients in a given room."""
        with self._lock:
            return [c for c in self._clients.values() if c.is_active and c.room_id == room_id]

    def get_inactive_clients(self, timeout_seconds: float) -> List[str]:
        """Finds user IDs whose last activity exceeded timeout_seconds."""
        now = time.time()
        with self._lock:
            inactive = []
            for uid, client in self._clients.items():
                if client.is_active and (now - client.last_active) > timeout_seconds:
                    inactive.append(uid)
            return inactive

    def count(self) -> int:
        """Returns total active connected clients."""
        with self._lock:
            return len(self._clients)
