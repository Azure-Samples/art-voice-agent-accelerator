"""
Thread-safe session management for concurrent conversation sessions.

Replaces the global _active_conversation_sessions dict with a thread-safe manager
to prevent race conditions during concurrent session add/remove operations.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import WebSocket

from utils.ml_logging import get_logger

logger = get_logger(__name__)


@dataclass
class SessionContext:
    """
    Container for active session state and metadata.

    Tracks the foundational objects required to service a conversation session
    and exposes concurrency-safe helpers for storing per-session metadata. The
    metadata helpers are intentionally async to signal when the event loop may
    yield control.
    """

    session_id: str
    memory_manager: Any
    websocket: WebSocket
    start_time: datetime = field(default_factory=datetime.now)
    _metadata: Dict[str, Any] = field(default_factory=dict)
    _metadata_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def get_metadata(self, key: str, default: Any = None) -> Any:
        """Return a metadata value, falling back to default when unset."""
        async with self._metadata_lock:
            return self._metadata.get(key, default)

    async def set_metadata(self, key: str, value: Any) -> None:
        """Persist a metadata value for this session."""
        async with self._metadata_lock:
            self._metadata[key] = value

    async def clear_metadata(self, key: Optional[str] = None) -> None:
        """Clear either a specific metadata key or the entire metadata dictionary."""
        async with self._metadata_lock:
            if key is None:
                self._metadata.clear()
            else:
                self._metadata.pop(key, None)

    async def metadata_snapshot(self) -> Dict[str, Any]:
        """Return a shallow copy of the current metadata for diagnostics."""
        async with self._metadata_lock:
            return dict(self._metadata)

    def get_metadata_nowait(self, key: str, default: Any = None) -> Any:
        """Best-effort metadata lookup without awaiting."""
        return self._metadata.get(key, default)

    def set_metadata_nowait(self, key: str, value: Any) -> None:
        """Best-effort metadata write without awaiting."""
        if not self._metadata_lock.locked():
            self._metadata[key] = value
            return

        # Fallback to async path when a coroutine currently holds the lock.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            loop.call_soon(loop.create_task, self.set_metadata(key, value))
        else:
            self._metadata[key] = value


class ThreadSafeSessionManager:
    """
    Thread-safe manager for active conversation sessions.

    Uses asyncio.Lock to protect concurrent access to session tracking,
    preventing race conditions during concurrent session management.
    """

    def __init__(self):
        self._sessions: Dict[str, SessionContext] = {}
        self._lock = asyncio.Lock()

    async def add_session(
        self,
        session_id: str,
        memory_manager: Any,
        websocket: WebSocket,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a conversation session thread-safely with optional metadata."""
        context = getattr(websocket.state, "session_context", None)
        if isinstance(context, SessionContext) and context.session_id == session_id:
            context.memory_manager = memory_manager
            context.websocket = websocket
        else:
            context = SessionContext(
                session_id=session_id,
                memory_manager=memory_manager,
                websocket=websocket,
            )
            try:
                websocket.state.session_context = context
            except Exception:
                pass
        if metadata:
            context._metadata.update(metadata)

        async with self._lock:
            self._sessions[session_id] = context
            logger.info(
                "Added conversation session %s. Total sessions: %s",
                session_id,
                len(self._sessions),
            )

    async def remove_session(self, session_id: str) -> bool:
        """Remove a conversation session thread-safely. Returns True if removed."""
        async with self._lock:
            context = self._sessions.pop(session_id, None)
            if context:
                try:
                    if getattr(context.websocket.state, "session_context", None) is context:
                        delattr(context.websocket.state, "session_context")
                except Exception:
                    pass
                logger.info(
                    "Removed conversation session %s. Remaining sessions: %s",
                    session_id,
                    len(self._sessions),
                )
                return True
            return False

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data thread-safely. Deprecated: prefer get_session_context."""
        context = await self.get_session_context(session_id)
        if not context:
            return None
        return {
            "memory_manager": context.memory_manager,
            "websocket": context.websocket,
            "start_time": context.start_time,
            "metadata": await context.metadata_snapshot(),
        }

    async def get_session_context(self, session_id: str) -> Optional[SessionContext]:
        """Return the SessionContext for an active session."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def get_session_count(self) -> int:
        """Get current session count thread-safely."""
        async with self._lock:
            return len(self._sessions)

    async def get_all_sessions_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Get a thread-safe snapshot of all sessions."""
        async with self._lock:
            sessions = list(self._sessions.items())

        snapshot: Dict[str, Dict[str, Any]] = {}
        for session_id, context in sessions:
            snapshot[session_id] = {
                "memory_manager": context.memory_manager,
                "websocket": context.websocket,
                "start_time": context.start_time,
            }
        return snapshot

    async def cleanup_stale_sessions(self, max_age_hours: int = 24) -> int:
        """Remove sessions older than max_age_hours and return count of removed sessions."""
        removed_count = 0
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        async with self._lock:
            stale_sessions = [
                session_id
                for session_id, session_context in self._sessions.items()
                if session_context.start_time < cutoff_time
            ]

            for session_id in stale_sessions:
                del self._sessions[session_id]
                removed_count += 1

            if removed_count > 0:
                logger.info(
                    "🧹 Cleaned up %s stale sessions. Remaining: %s",
                    removed_count,
                    len(self._sessions),
                )

        return removed_count

    async def get_metadata(self, session_id: str, key: str, default: Any = None) -> Any:
        """Fetch a metadata value for a session if it exists."""
        context = await self.get_session_context(session_id)
        if not context:
            return default
        return await context.get_metadata(key, default)

    async def set_metadata(self, session_id: str, key: str, value: Any) -> bool:
        """Store a metadata value for a session. Returns False when the session is missing."""
        context = await self.get_session_context(session_id)
        if not context:
            return False
        await context.set_metadata(key, value)
        return True

    async def clear_metadata(
        self,
        session_id: str,
        key: Optional[str] = None,
    ) -> bool:
        """Clear metadata values for a session."""
        context = await self.get_session_context(session_id)
        if not context:
            return False
        await context.clear_metadata(key)
        return True
