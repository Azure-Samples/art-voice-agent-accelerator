"""
Thread-safe WebSocket client management for concurrent ACS calls.

.. deprecated::
    This module is deprecated and not used in the main application.
    The ThreadSafeConnectionManager in connection_manager.py provides
    more comprehensive WebSocket connection management with Redis pub/sub.

    Kept for backward compatibility with sample code in samples/labs/dev/.

This module provides a thread-safe replacement for the shared app.state.clients set
to prevent race conditions with concurrent WebSocket connections.
"""

import asyncio

from fastapi import WebSocket
from utils.ml_logging import get_logger

logger = get_logger(__name__)


class ThreadSafeWebSocketManager:
    """
    Thread-safe manager for WebSocket clients.

    Uses asyncio.Lock to protect concurrent access to the client set,
    preventing race conditions during add/remove/iteration operations.
    """

    def __init__(self):
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add_client(self, websocket: WebSocket) -> None:
        """Add a WebSocket client thread-safely."""
        async with self._lock:
            self._clients.add(websocket)
            logger.info(f"Added WebSocket client. Total clients: {len(self._clients)}")

    async def remove_client(self, websocket: WebSocket) -> bool:
        """Remove a WebSocket client thread-safely. Returns True if removed."""
        async with self._lock:
            if websocket in self._clients:
                self._clients.remove(websocket)
                logger.info(f"Removed WebSocket client. Total clients: {len(self._clients)}")
                return True
            return False

    async def get_clients_snapshot(self) -> set[WebSocket]:
        """Get a thread-safe snapshot of current clients for iteration."""
        async with self._lock:
            # Return a copy to prevent external modification during iteration
            return self._clients.copy()

    async def get_client_count(self) -> int:
        """Get current client count thread-safely."""
        async with self._lock:
            return len(self._clients)

    async def cleanup_disconnected(self) -> int:
        """Remove disconnected clients and return count of removed clients."""
        removed_count = 0
        async with self._lock:
            disconnected = [
                client
                for client in self._clients
                if client.client_state.value not in (1, 2)  # Not CONNECTING or CONNECTED
            ]
            for client in disconnected:
                self._clients.discard(client)
                removed_count += 1

            if removed_count > 0:
                logger.info(
                    f"Cleaned up {removed_count} disconnected clients. Remaining: {len(self._clients)}"
                )

        return removed_count
