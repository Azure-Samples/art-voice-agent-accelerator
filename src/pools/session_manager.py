"""
Thread-safe session management for concurrent conversation sessions.

Replaces the global _active_conversation_sessions dict with a thread-safe manager
to prevent race conditions during concurrent session add/remove operations.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import WebSocket

from utils.ml_logging import get_logger

logger = get_logger(__name__)


class ThreadSafeSessionManager:
    """
    Thread-safe manager for active conversation sessions.

    Uses asyncio.Lock to protect concurrent access to session tracking,
    preventing race conditions during concurrent session management.
    """

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def add_session(
        self, session_id: str, memory_manager: Any, websocket: WebSocket
    ) -> None:
        """Add a conversation session thread-safely."""
        async with self._lock:
            self._sessions[session_id] = {
                "memory_manager": memory_manager,
                "websocket": websocket,
                "start_time": datetime.now(),
            }
            logger.info(
                f"Added conversation session {session_id}. Total sessions: {len(self._sessions)}"
            )

    async def remove_session(self, session_id: str) -> bool:
        """Remove a conversation session thread-safely. Returns True if removed."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(
                    f"Removed conversation session {session_id}. Remaining sessions: {len(self._sessions)}"
                )
                return True
            return False

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data thread-safely."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def get_session_count(self) -> int:
        """Get current session count thread-safely."""
        async with self._lock:
            return len(self._sessions)

    async def get_all_sessions_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Get a thread-safe snapshot of all sessions."""
        async with self._lock:
            return self._sessions.copy()

    async def cleanup_stale_sessions(self, max_age_hours: int = 24) -> int:
        """Remove sessions older than max_age_hours and return count of removed sessions."""
        removed_count = 0
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        async with self._lock:
            stale_sessions = [
                session_id
                for session_id, session_data in self._sessions.items()
                if session_data.get("start_time", datetime.now()) < cutoff_time
            ]

            for session_id in stale_sessions:
                del self._sessions[session_id]
                removed_count += 1

            if removed_count > 0:
                logger.info(
                    f"🧹 Cleaned up {removed_count} stale sessions. Remaining: {len(self._sessions)}"
                )

        return removed_count
