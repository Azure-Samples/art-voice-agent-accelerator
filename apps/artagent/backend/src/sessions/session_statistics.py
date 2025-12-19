"""
Session Statistics Management
============================

Centralized service for tracking and persisting session statistics across
ACS media and realtime conversation endpoints.

Features:
- Active session tracking for both media and realtime
- Total disconnection counters with persistent storage
- Thread-safe operations with async support
- Integration with CosmosDB for persistence
- Unified statistics interface for both endpoints
"""

import asyncio
from datetime import datetime
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import SpanKind
from utils.ml_logging import get_logger

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


class SessionStatisticsManager:
    """
    Centralized manager for session statistics across media and realtime endpoints.

    Provides unified tracking of:
    - Active sessions (media handlers and conversation sessions)
    - Total disconnection counters (persisted across restarts)
    - Thread-safe operations
    """

    def __init__(self, cosmos_manager: Any | None = None):
        """
        Initialize session statistics manager.

        :param cosmos_manager: CosmosDB manager for persistence
        """
        self._lock = asyncio.Lock()
        self._active_media_sessions: dict[str, dict[str, Any]] = {}
        self._active_realtime_sessions: dict[str, dict[str, Any]] = {}
        self._total_disconnected_count = 0
        self._cosmos_manager = cosmos_manager
        self._stats_collection_name = "session_statistics"

    async def initialize(self) -> None:
        """
        Initialize statistics manager and load persistent counters.
        """
        with tracer.start_span("session_stats_initialize", kind=SpanKind.INTERNAL) as span:
            try:
                await self._load_persistent_counters()
                span.set_attribute("session_stats.initialization", "success")
                logger.info("Session statistics manager initialized successfully")
            except Exception as e:
                span.set_attribute("session_stats.initialization", "failed")
                span.record_exception(e)
                logger.error(f"Failed to initialize session statistics manager: {e}")
                raise

    async def _load_persistent_counters(self) -> None:
        """
        Load persistent counters from storage.
        """
        if not self._cosmos_manager:
            logger.warning("No CosmosDB manager available, using in-memory counters")
            return

        try:
            stats_doc = await self._get_stats_document()
            if stats_doc:
                self._total_disconnected_count = stats_doc.get("total_disconnected", 0)
                logger.info(
                    f"Loaded persistent total disconnected count: {self._total_disconnected_count}"
                )
            else:
                await self._create_initial_stats_document()
                logger.info("Created initial session statistics document")
        except Exception as e:
            logger.error(f"Failed to load persistent counters: {e}")
            # Continue with in-memory only

    async def _get_stats_document(self) -> dict[str, Any] | None:
        """
        Get the global statistics document from storage.
        """
        try:
            collection = self._cosmos_manager.database[self._stats_collection_name]
            stats_doc = collection.find_one({"_id": "global_session_stats"})
            return stats_doc
        except Exception as e:
            logger.error(f"Failed to get stats document: {e}")
            return None

    async def _create_initial_stats_document(self) -> None:
        """
        Create initial statistics document in storage.
        """
        try:
            collection = self._cosmos_manager.database[self._stats_collection_name]
            initial_doc = {
                "_id": "global_session_stats",
                "total_disconnected": 0,
                "created_at": datetime.utcnow().isoformat(),
                "last_updated": datetime.utcnow().isoformat(),
            }
            collection.insert_one(initial_doc)
        except Exception as e:
            logger.error(f"Failed to create initial stats document: {e}")

    async def _persist_counter_update(self) -> None:
        """
        Persist the current disconnection counter to storage.
        """
        if not self._cosmos_manager:
            return

        try:
            collection = self._cosmos_manager.database[self._stats_collection_name]
            collection.update_one(
                {"_id": "global_session_stats"},
                {
                    "$set": {
                        "total_disconnected": self._total_disconnected_count,
                        "last_updated": datetime.utcnow().isoformat(),
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.error(f"Failed to persist counter update: {e}")

    async def add_media_session(self, call_connection_id: str, handler: Any) -> None:
        """
        Add an active media session.

        :param call_connection_id: The ACS call connection ID
        :param handler: The media handler instance
        """
        async with self._lock:
            self._active_media_sessions[call_connection_id] = {
                "handler": handler,
                "session_type": "media",
                "start_time": datetime.utcnow(),
                "call_connection_id": call_connection_id,
            }
            logger.info(
                f"Added media session {call_connection_id}. Active media sessions: {len(self._active_media_sessions)}"
            )

    async def remove_media_session(self, call_connection_id: str) -> bool:
        """
        Remove a media session and increment disconnection counter.

        :param call_connection_id: The ACS call connection ID
        :return: True if session was removed, False if not found
        """
        async with self._lock:
            if call_connection_id in self._active_media_sessions:
                del self._active_media_sessions[call_connection_id]
                self._total_disconnected_count += 1

                logger.info(
                    f"Removed media session {call_connection_id}. "
                    f"Active media sessions: {len(self._active_media_sessions)}, "
                    f"Total disconnected: {self._total_disconnected_count}"
                )

                # Persist the counter update
                await self._persist_counter_update()
                return True
            return False

    async def add_realtime_session(
        self, session_id: str, memory_manager: Any, websocket: Any
    ) -> None:
        """
        Add an active realtime conversation session.

        :param session_id: The session identifier
        :param memory_manager: The memory manager instance
        :param websocket: The WebSocket connection
        """
        async with self._lock:
            self._active_realtime_sessions[session_id] = {
                "memory_manager": memory_manager,
                "websocket": websocket,
                "session_type": "realtime",
                "start_time": datetime.utcnow(),
            }
            logger.info(
                f"Added realtime session {session_id}. Active realtime sessions: {len(self._active_realtime_sessions)}"
            )

    async def remove_realtime_session(self, session_id: str) -> bool:
        """
        Remove a realtime session and increment disconnection counter.

        :param session_id: The session identifier
        :return: True if session was removed, False if not found
        """
        async with self._lock:
            if session_id in self._active_realtime_sessions:
                del self._active_realtime_sessions[session_id]
                self._total_disconnected_count += 1

                logger.info(
                    f"Removed realtime session {session_id}. "
                    f"Active realtime sessions: {len(self._active_realtime_sessions)}, "
                    f"Total disconnected: {self._total_disconnected_count}"
                )

                # Persist the counter update
                await self._persist_counter_update()
                return True
            return False

    async def get_statistics(self) -> dict[str, Any]:
        """
        Get comprehensive session statistics.

        :return: Dictionary containing all session statistics
        """
        async with self._lock:
            return {
                "active_sessions": {
                    "media": len(self._active_media_sessions),
                    "realtime": len(self._active_realtime_sessions),
                    "total": len(self._active_media_sessions) + len(self._active_realtime_sessions),
                },
                "total_disconnected": self._total_disconnected_count,
                "session_details": {
                    "media_sessions": list(self._active_media_sessions.keys()),
                    "realtime_sessions": list(self._active_realtime_sessions.keys()),
                },
            }

    async def get_active_media_count(self) -> int:
        """Get count of active media sessions."""
        async with self._lock:
            return len(self._active_media_sessions)

    async def get_active_realtime_count(self) -> int:
        """Get count of active realtime sessions."""
        async with self._lock:
            return len(self._active_realtime_sessions)

    async def get_total_active_count(self) -> int:
        """Get total count of all active sessions."""
        async with self._lock:
            return len(self._active_media_sessions) + len(self._active_realtime_sessions)

    async def get_total_disconnected_count(self) -> int:
        """Get total disconnection count."""
        async with self._lock:
            return self._total_disconnected_count
