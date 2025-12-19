"""
Thread-safe session metrics for concurrent ACS calls.

Provides atomic counters to prevent race conditions in session tracking.
"""

import asyncio
from datetime import datetime
from typing import Any

from utils.ml_logging import get_logger

logger = get_logger(__name__)


class ThreadSafeSessionMetrics:
    """
    Thread-safe session metrics manager.

    Uses asyncio.Lock to protect concurrent access to metrics counters,
    preventing lost updates during concurrent session management.

    Tracks:
    - active_connections: Current number of open WebSocket connections (real-time)
    - total_connected: Historical count of all connections ever made
    - total_disconnected: Historical count of all disconnections
    """

    def __init__(self):
        self._metrics: dict[str, Any] = {
            "active_connections": 0,  # Current active WebSocket connections (real-time)
            "total_connected": 0,  # Historical total connections made
            "total_disconnected": 0,  # Historical total disconnections
            "last_updated": datetime.utcnow().isoformat(),
        }
        self._lock = asyncio.Lock()

    async def increment_connected(self) -> int:
        """
        Atomically increment both active and total connected counters.
        Called when a WebSocket connection is established.
        Returns the new active connection count.
        """
        async with self._lock:
            self._metrics["active_connections"] += 1
            self._metrics["total_connected"] += 1
            self._metrics["last_updated"] = datetime.utcnow().isoformat()
            active_count = self._metrics["active_connections"]
            total_count = self._metrics["total_connected"]
            logger.info(f"WS Connected: Active={active_count}, Total={total_count}")
            return active_count

    async def increment_disconnected(self) -> int:
        """
        Atomically decrement active and increment total disconnected counters.
        Called when a WebSocket connection is closed.
        Returns the new active connection count.
        """
        async with self._lock:
            # Decrement active connections (but not below 0)
            self._metrics["active_connections"] = max(0, self._metrics["active_connections"] - 1)
            # Increment total disconnected counter
            self._metrics["total_disconnected"] += 1
            self._metrics["last_updated"] = datetime.utcnow().isoformat()
            active_count = self._metrics["active_connections"]
            total_disconnected = self._metrics["total_disconnected"]
            logger.info(
                f"WS Disconnected: Active={active_count}, TotalDisconnected={total_disconnected}"
            )
            return active_count

    async def get_snapshot(self) -> dict[str, Any]:
        """Get a thread-safe snapshot of current metrics."""
        async with self._lock:
            return self._metrics.copy()

    async def get_active_sessions(self) -> int:
        """Get current number of active sessions (real-time active connections)."""
        async with self._lock:
            return self._metrics["active_connections"]
