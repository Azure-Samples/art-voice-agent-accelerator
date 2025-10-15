"""
Clean WebSocket Connection Manager
=================================

Simple, production-ready WebSocket connection management following FastAPI best practices.

Features:
- Thread-safe connection registry with async locks
- Per-connection send queues to prevent concurrent write issues
- Simple broadcast by session, call, topic, or all connections
- Clean lifecycle management with proper resource cleanup
- Production logging and error handling
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Set, Literal

from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from utils.ml_logging import get_logger

logger = get_logger(__name__)

ClientType = Literal["dashboard", "conversation", "media", "other"]


@dataclass
class ConnectionMeta:
    """Simple connection metadata for routing."""

    connection_id: str
    client_type: ClientType = "other"
    session_id: Optional[str] = None
    call_id: Optional[str] = None
    user_id: Optional[str] = None
    topics: Set[str] = field(default_factory=set)
    handler: Optional[Any] = None
    created_at: float = field(default_factory=time.time)


class _Connection:
    """Internal connection wrapper with send queue and proper thread safety."""

    def __init__(
        self,
        websocket: WebSocket,
        meta: ConnectionMeta,
        on_send_failure: Optional[Callable[[Exception], Awaitable[None]]] = None,
    ):
        self.ws = websocket
        self.meta = meta
        self._queue = asyncio.Queue(maxsize=100)  # Simple queue with reasonable limit
        self._sender_task = asyncio.create_task(self._sender_loop())
        self._send_lock = asyncio.Lock()  # Protect send operations
        self._closed = False
        self._on_send_failure = on_send_failure

    async def send_json(self, payload: Dict[str, Any]) -> None:
        """Queue JSON message for sending with thread safety."""
        if self._closed:
            return

        async with self._send_lock:  # Protect queue operations
            try:
                message = json.dumps(payload)
                if self._queue.full():
                    # Atomic drop-oldest-and-add operation
                    try:
                        self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                await self._queue.put(message)
            except Exception as e:
                logger.error(
                    f"Failed to queue message: {e}",
                    extra={"conn_id": self.meta.connection_id},
                )

    async def _sender_loop(self) -> None:
        """Send queued messages to WebSocket with proper error handling."""
        try:
            while not self._closed:
                try:
                    message = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue  # Check _closed flag periodically

                if message is None:  # Shutdown signal
                    return

                # Thread-safe WebSocket state check and send
                try:
                    if (
                        self.ws.client_state == WebSocketState.CONNECTED
                        and self.ws.application_state == WebSocketState.CONNECTED
                    ):
                        await self.ws.send_text(message)
                    else:
                        logger.debug(
                            "WebSocket no longer connected; stopping sender",
                            extra={"conn_id": self.meta.connection_id},
                        )
                        self._closed = True
                        if self._on_send_failure:
                            asyncio.create_task(self._on_send_failure(RuntimeError("websocket_disconnected")))
                        return
                except Exception as e:
                    level = logger.error
                    message = str(e) if e else ""
                    if isinstance(e, RuntimeError) and "close message" in message.lower():
                        level = logger.info
                    level(
                        "WebSocket send failed: %s",
                        message,
                        extra={"conn_id": self.meta.connection_id},
                    )
                    self._closed = True
                    if self._on_send_failure:
                        asyncio.create_task(self._on_send_failure(e))
                    return

        except asyncio.CancelledError:
            logger.debug(
                f"Sender loop cancelled", extra={"conn_id": self.meta.connection_id}
            )
        except Exception as e:
            logger.error(
                f"Sender loop error: {e}", extra={"conn_id": self.meta.connection_id}
            )

    async def close(self) -> None:
        """Close connection and cleanup resources with proper thread safety."""
        if self._closed:
            return

        self._closed = True

        async with self._send_lock:  # Ensure no concurrent send operations
            try:
                # Signal sender to stop via sentinel; ensure it enqueues even if full
                try:
                    self._queue.put_nowait(None)
                except asyncio.QueueFull:
                    # Drop one oldest and try again to guarantee shutdown signal
                    try:
                        _ = self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        self._queue.put_nowait(None)
                    except asyncio.QueueFull:
                        # As last resort, rely on timeout + _closed flag in loop
                        logger.debug(
                            "Queue full during close; relying on timeout/_closed to exit",
                            extra={"conn_id": self.meta.connection_id},
                        )

                # Allow sender task to exit gracefully (sentinel or _closed flag)
                if not self._sender_task.done():
                    try:
                        await asyncio.wait_for(self._sender_task, timeout=2.0)
                    except asyncio.TimeoutError:
                        logger.debug(
                            "Sender task timeout on close; proceeding to force close",
                            extra={"conn_id": self.meta.connection_id},
                        )

                # Close WebSocket if still connected
                try:
                    if (
                        self.ws.client_state == WebSocketState.CONNECTED
                        and self.ws.application_state == WebSocketState.CONNECTED
                    ):
                        await self.ws.close()
                except Exception as e:
                    logger.debug(
                        f"Error closing WebSocket: {e}",
                        extra={"conn_id": self.meta.connection_id},
                    )

            except Exception as e:
                logger.error(
                    f"Error during connection cleanup: {e}",
                    extra={"conn_id": self.meta.connection_id},
                )


class ThreadSafeConnectionManager:
    """
    Clean WebSocket connection manager for production use with connection limits.

    Simple API:
    - register() - Add new WebSocket connection (with limit enforcement)
    - unregister() - Remove connection
    - send_to_connection() - Send to specific connection
    - broadcast_*() - Send to multiple connections
    - stats() - Get connection statistics

    Phase 1 Features:
    - Connection limit enforcement (200 max by default)
    - Connection queue for overflow handling
    - Automatic rejection of excess connections
    """

    def __init__(
        self,
        max_connections: int = 200,
        queue_size: int = 50,
        enable_connection_limits: bool = True,
    ):
        self._lock = asyncio.Lock()
        self._conns: Dict[str, _Connection] = {}

        # Simple indexes for efficient broadcast
        self._by_session: Dict[str, Set[str]] = {}
        self._by_call: Dict[str, Set[str]] = {}
        self._by_topic: Dict[str, Set[str]] = {}

        # Connection limit management
        self.max_connections = max_connections
        self.queue_size = queue_size
        self.enable_limits = enable_connection_limits
        self._connection_queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self._rejected_count = 0

        # Out-of-band per-call context (for pre-initialized resources before WS exists)
        # Example: { call_id: { "lva_agent": <agent>, "pool": <pool>, "session_id": str, ... } }
        self._call_context: Dict[str, Any] = {}

        logger.info(
            f"ConnectionManager initialized: max_connections={max_connections}, "
            f"queue_size={queue_size}, limits_enabled={enable_connection_limits}"
        )

    async def stop(self) -> None:
        """Stop manager and close all connections."""
        async with self._lock:
            close_tasks = [conn.close() for conn in self._conns.values()]
        await asyncio.gather(*close_tasks, return_exceptions=True)

        async with self._lock:
            self._conns.clear()
            self._by_session.clear()
            self._by_call.clear()
            self._by_topic.clear()

    async def register(
        self,
        websocket: WebSocket,
        *,
        client_type: ClientType = "other",
        session_id: Optional[str] = None,
        call_id: Optional[str] = None,
        user_id: Optional[str] = None,
        topics: Optional[Set[str]] = None,
        handler: Optional[Any] = None,
        accept_already_done: bool = True,
    ) -> str:
        """
        Register a WebSocket connection with connection limit enforcement.

        Args:
            websocket: WebSocket instance (will be accepted if accept_already_done=False)
            client_type: Type of client (dashboard, conversation, media, other)
            session_id: Optional session identifier
            call_id: Optional ACS call connection ID
            user_id: Optional user identifier
            topics: Optional set of topics for broadcasting
            handler: Optional handler instance for lifecycle management
            accept_already_done: If False, will call websocket.accept()

        Returns:
            str: Generated connection ID

        Raises:
            RuntimeError: If connection limit exceeded and queue is full
        """
        # Phase 1: Check connection limits before accepting
        if self.enable_limits:
            async with self._lock:
                current_count = len(self._conns)

            if current_count >= self.max_connections:
                # Try to queue the connection
                try:
                    if self._connection_queue.full():
                        self._rejected_count += 1
                        logger.warning(
                            f"Connection rejected: limit={self.max_connections}, "
                            f"current={current_count}, queue_full=True, "
                            f"total_rejected={self._rejected_count}"
                        )
                        raise RuntimeError(
                            f"Connection limit exceeded: {current_count}/{self.max_connections} "
                            "and queue is full. Please try again later."
                        )

                    logger.info(
                        f"Connection queued: current={current_count}/{self.max_connections}, "
                        f"queue_size={self._connection_queue.qsize()}"
                    )
                    # This would require more complex implementation for actual queuing
                    # For now, we reject when at limit
                    self._rejected_count += 1
                    raise RuntimeError(
                        f"Connection limit exceeded: {current_count}/{self.max_connections}. "
                        "Please try again later."
                    )

                except asyncio.QueueFull:
                    self._rejected_count += 1
                    logger.warning(
                        f"Connection rejected: limit={self.max_connections}, "
                        f"current={current_count}, queue_full=True"
                    )
                    raise RuntimeError("Server at capacity. Please try again later.")

        if not accept_already_done:
            try:
                await websocket.accept()
            except Exception as e:
                logger.error(f"Failed to accept WebSocket: {e}")
                raise RuntimeError("WebSocket accept failed") from e

        conn_id = str(uuid.uuid4())
        meta = ConnectionMeta(
            connection_id=conn_id,
            client_type=client_type,
            session_id=session_id,
            call_id=call_id,
            user_id=user_id,
            topics=topics or set(),
            handler=handler,
        )
        async def _on_send_failure(exc: Exception, conn_id: str = conn_id):
            await self._handle_connection_send_failure(conn_id, exc)

        conn = _Connection(
            websocket=websocket,
            meta=meta,
            on_send_failure=_on_send_failure,
        )

        async with self._lock:
            self._conns[conn_id] = conn
            if session_id:
                self._by_session.setdefault(session_id, set()).add(conn_id)
            if call_id:
                self._by_call.setdefault(call_id, set()).add(conn_id)
            for topic in meta.topics:
                self._by_topic.setdefault(topic, set()).add(conn_id)

        logger.info(
            f"WebSocket registered: {conn_id} ({client_type}) "
            f"[{len(self._conns)}/{self.max_connections if self.enable_limits else '∞'}]",
            extra={"conn_id": conn_id, "session_id": session_id, "call_id": call_id},
        )
        return conn_id

    async def _handle_connection_send_failure(
        self, connection_id: str, exc: Exception
    ) -> None:
        """Automatically unregister connections whose sender loop failed."""
        msg = str(exc) if exc else ""
        if msg:
            logger.info(
                "Scheduling cleanup for connection %s after send failure: %s",
                connection_id,
                msg,
            )
        else:
            logger.info(
                "Scheduling cleanup for connection %s after send failure",
                connection_id,
            )

        try:
            await self.unregister(connection_id)
        except Exception as cleanup_error:
            logger.error(
                "Error during send-failure cleanup for %s: %s",
                connection_id,
                cleanup_error,
            )

    async def unregister(self, connection_id: str) -> None:
        """Remove connection and cleanup resources."""
        async with self._lock:
            conn = self._conns.pop(connection_id, None)
            if not conn:
                return

            # Cleanup handler if present
            if conn.meta.handler:
                try:
                    if hasattr(conn.meta.handler, "stop") and callable(
                        conn.meta.handler.stop
                    ):
                        await conn.meta.handler.stop()
                except Exception as e:
                    logger.error(
                        f"Error stopping handler: {e}", extra={"conn_id": connection_id}
                    )

            # Remove from indexes
            if conn.meta.session_id:
                self._by_session.get(conn.meta.session_id, set()).discard(connection_id)
            if conn.meta.call_id:
                self._by_call.get(conn.meta.call_id, set()).discard(connection_id)
            for topic in conn.meta.topics:
                self._by_topic.get(topic, set()).discard(connection_id)

        await conn.close()
        logger.info(f"WebSocket unregistered: {connection_id}")

    async def unregister_by_websocket(self, websocket: WebSocket) -> None:
        """Unregister connection by WebSocket instance."""
        target_id = None
        async with self._lock:
            for conn_id, conn in self._conns.items():
                if conn.ws is websocket:
                    target_id = conn_id
                    break
        if target_id:
            await self.unregister(target_id)

    async def stats(self) -> Dict[str, Any]:
        """Get connection statistics with Phase 1 metrics."""
        async with self._lock:
            return {
                "connections": len(self._conns),
                "max_connections": self.max_connections if self.enable_limits else None,
                "utilization_percent": round(
                    len(self._conns) / self.max_connections * 100, 1
                )
                if self.enable_limits
                else None,
                "rejected_count": self._rejected_count,
                "queue_size": self._connection_queue.qsize(),
                "queue_capacity": self.queue_size,
                "limits_enabled": self.enable_limits,
                "by_session": {k: len(v) for k, v in self._by_session.items()},
                "by_call": {k: len(v) for k, v in self._by_call.items()},
                "by_topic": {k: len(v) for k, v in self._by_topic.items()},
            }

    async def send_to_connection(
        self, connection_id: str, payload: Dict[str, Any]
    ) -> bool:
        """
        Send message to specific connection.

        Returns:
            bool: True if sent successfully, False if connection not found
        """
        async with self._lock:
            conn = self._conns.get(connection_id)
        if conn:
            await conn.send_json(payload)
            return True
        return False

    async def broadcast_session(self, session_id: str, payload: Dict[str, Any]) -> int:
        """
        Broadcast to all connections in a session with session-safe data filtering.

        This ensures the frontend can only grab data concerning that session,
        providing proper session isolation and security.
        """
        async with self._lock:
            conn_ids = list(self._by_session.get(session_id, set()))
            targets = [self._conns[i] for i in conn_ids if i in self._conns]

        # Add session context to payload for frontend filtering
        session_payload = {
            **payload,
            "session_context": {
                "session_id": session_id,
                "restricted_to_session": True,
                "timestamp": time.time(),
            },
        }

        sent = 0
        failed_connections = []

        # Use asyncio.gather with return_exceptions for better error handling
        tasks = []
        for conn in targets:
            tasks.append(self._safe_send_to_connection(conn, session_payload))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_connections.append(targets[i].meta.connection_id)
                logger.error(
                    f"Session broadcast failed: {result}",
                    extra={
                        "conn_id": targets[i].meta.connection_id,
                        "session_id": session_id,
                    },
                )
            else:
                sent += 1

        # Clean up failed connections asynchronously
        if failed_connections:
            asyncio.create_task(self._cleanup_failed_connections(failed_connections))

        return sent

    async def _safe_send_to_connection(
        self, conn: "_Connection", payload: Dict[str, Any]
    ) -> None:
        """Safely send to a connection with proper error handling."""
        try:
            await conn.send_json(payload)
        except Exception as e:
            # Re-raise for gather() to handle
            raise e

    async def _cleanup_failed_connections(self, failed_conn_ids: list[str]) -> None:
        """Clean up failed connections in background."""
        for conn_id in failed_conn_ids:
            try:
                await self.unregister(conn_id)
                logger.info(f"Auto-removed failed connection: {conn_id}")
            except Exception as e:
                logger.error(f"Error removing failed connection {conn_id}: {e}")

    async def broadcast_call(self, call_id: str, payload: Dict[str, Any]) -> int:
        """Broadcast to all connections in a call."""
        async with self._lock:
            conn_ids = list(self._by_call.get(call_id, set()))
            targets = [self._conns[i] for i in conn_ids if i in self._conns]

        sent = 0
        for conn in targets:
            try:
                await conn.send_json(payload)
                sent += 1
            except Exception as e:
                logger.error(
                    f"Broadcast failed: {e}", extra={"conn_id": conn.meta.connection_id}
                )
        return sent

    async def broadcast_topic(self, topic: str, payload: Dict[str, Any]) -> int:
        """Broadcast to all connections subscribed to a topic."""
        async with self._lock:
            conn_ids = list(self._by_topic.get(topic, set()))
            targets = [self._conns[i] for i in conn_ids if i in self._conns]

        sent = 0
        for conn in targets:
            try:
                await conn.send_json(payload)
                sent += 1
            except Exception as e:
                logger.error(
                    f"Broadcast failed: {e}", extra={"conn_id": conn.meta.connection_id}
                )
        return sent

    async def broadcast_all(self, payload: Dict[str, Any]) -> int:
        """Broadcast to all connections."""
        async with self._lock:
            targets = list(self._conns.values())

        sent = 0
        for conn in targets:
            try:
                await conn.send_json(payload)
                sent += 1
            except Exception as e:
                logger.error(
                    f"Broadcast failed: {e}", extra={"conn_id": conn.meta.connection_id}
                )
        return sent

    async def get_connection_meta(self, connection_id: str) -> Optional[ConnectionMeta]:
        """Get connection metadata safely."""
        async with self._lock:
            conn = self._conns.get(connection_id)
            return conn.meta if conn else None

    # ---------------------- Call Context (Out-of-band) ---------------------- #
    async def set_call_context(self, call_id: str, context: Dict[str, Any]) -> None:
        """Associate arbitrary context with a call_id (thread-safe)."""
        async with self._lock:
            self._call_context[call_id] = context

    async def get_call_context(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get (without removing) context for a call_id (thread-safe)."""
        async with self._lock:
            return self._call_context.get(call_id)

    async def pop_call_context(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Atomically retrieve and remove context for a call_id (thread-safe)."""
        async with self._lock:
            return self._call_context.pop(call_id, None)

    async def get_connection_by_call_id(self, call_id: str) -> Optional[str]:
        """Get connection_id by call_id safely."""
        async with self._lock:
            conn_ids = self._by_call.get(call_id, set())
            return next(iter(conn_ids), None) if conn_ids else None

    async def get_session_data_safe(
        self, session_id: str, requesting_connection_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get session data safely - only if the requesting connection belongs to that session.

        This ensures frontend can only access data from their own session,
        providing proper session isolation and security.
        """
        async with self._lock:
            # Check if requesting connection belongs to this session
            requesting_conn = self._conns.get(requesting_connection_id)
            if not requesting_conn or requesting_conn.meta.session_id != session_id:
                logger.warning(
                    f"Unauthorized session data access attempt",
                    extra={
                        "requesting_conn_id": requesting_connection_id,
                        "requested_session_id": session_id,
                        "actual_session_id": requesting_conn.meta.session_id
                        if requesting_conn
                        else None,
                    },
                )
                return None

            # Get all connections in this session
            session_conn_ids = self._by_session.get(session_id, set())
            session_connections = [
                {
                    "connection_id": conn_id,
                    "client_type": self._conns[conn_id].meta.client_type,
                    "call_id": self._conns[conn_id].meta.call_id,
                    "user_id": self._conns[conn_id].meta.user_id,
                    "topics": list(self._conns[conn_id].meta.topics),
                    "created_at": self._conns[conn_id].meta.created_at,
                }
                for conn_id in session_conn_ids
                if conn_id in self._conns
            ]

            return {
                "session_id": session_id,
                "connections": session_connections,
                "connection_count": len(session_connections),
                "timestamp": time.time(),
                "restricted_to_session": True,
            }

    async def get_connection_by_websocket(self, websocket: WebSocket) -> Optional[str]:
        """Get connection_id by WebSocket instance safely."""
        async with self._lock:
            for conn_id, conn in self._conns.items():
                if conn.ws is websocket:
                    return conn_id
        return None

    async def validate_and_cleanup_stale_connections(self) -> Dict[str, int]:
        """
        Validate connection states and cleanup stale connections.

        Returns:
            Dict with cleanup statistics
        """
        async with self._lock:
            stale_conn_ids = []
            for conn_id, conn in self._conns.items():
                # Check if WebSocket is still connected
                if (
                    conn.ws.client_state != WebSocketState.CONNECTED
                    or conn.ws.application_state != WebSocketState.CONNECTED
                ):
                    stale_conn_ids.append(conn_id)

            # Remove stale connections
            for conn_id in stale_conn_ids:
                await self._cleanup_connection_unsafe(conn_id)

            return {
                "removed_stale": len(stale_conn_ids),
                "active_connections": len(self._conns),
                "max_connections": self.max_connections if self.enable_limits else None,
            }

    async def _cleanup_connection_unsafe(self, connection_id: str) -> None:
        """Internal cleanup without lock (assumes lock is held)."""
        conn = self._conns.pop(connection_id, None)
        if not conn:
            return

        # Cleanup handler if present
        if conn.meta.handler:
            try:
                if hasattr(conn.meta.handler, "stop") and callable(
                    conn.meta.handler.stop
                ):
                    await conn.meta.handler.stop()
            except Exception as e:
                logger.error(
                    f"Error stopping handler: {e}", extra={"conn_id": connection_id}
                )

        # Remove from indexes
        if conn.meta.session_id:
            self._by_session.get(conn.meta.session_id, set()).discard(connection_id)
        if conn.meta.call_id:
            self._by_call.get(conn.meta.call_id, set()).discard(connection_id)
        for topic in conn.meta.topics:
            self._by_topic.get(topic, set()).discard(connection_id)

        await conn.close()

    # Handler management - Direct, no legacy wrappers
    async def attach_handler(self, connection_id: str, handler: Any) -> bool:
        """Attach handler directly to connection."""
        async with self._lock:
            conn = self._conns.get(connection_id)
            if conn:
                conn.meta.handler = handler
                return True
        return False

    async def get_handler_by_call_id(self, call_id: str) -> Optional[Any]:
        """Get handler for a call_id - direct access."""
        async with self._lock:
            conn_ids = self._by_call.get(call_id, set())
            for conn_id in conn_ids:
                conn = self._conns.get(conn_id)
                if conn and conn.meta.handler:
                    return conn.meta.handler
        return None

    async def get_handler_by_connection_id(self, connection_id: str) -> Optional[Any]:
        """Get handler for a connection_id - direct access."""
        async with self._lock:
            conn = self._conns.get(connection_id)
            return conn.meta.handler if conn else None

    # Enhanced Session-Specific Broadcasting for Frontend Data Isolation
    async def get_session_data(self, session_id: str) -> Dict[str, Any]:
        """
        Get all data for a specific session - thread-safe for frontend consumption.

        Frontend can call this to get only data from their session.
        """
        async with self._lock:
            conn_ids = self._by_session.get(session_id, set())
            connections = []

            for conn_id in conn_ids:
                conn = self._conns.get(conn_id)
                if conn:
                    connections.append(
                        {
                            "connection_id": conn_id,
                            "client_type": conn.meta.client_type,
                            "call_id": conn.meta.call_id,
                            "user_id": conn.meta.user_id,
                            "topics": list(conn.meta.topics),
                            "created_at": conn.meta.created_at,
                            "connected": (
                                conn.ws.client_state == WebSocketState.CONNECTED
                                and conn.ws.application_state
                                == WebSocketState.CONNECTED
                            ),
                        }
                    )

            return {
                "session_id": session_id,
                "connections": connections,
                "connection_count": len(connections),
                "active_connections": sum(1 for c in connections if c["connected"]),
            }

    async def broadcast_session_with_metadata(
        self, session_id: str, payload: Dict[str, Any], include_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Enhanced session broadcast with metadata for frontend isolation.

        Returns detailed broadcast results for frontend consumption.
        """
        async with self._lock:
            conn_ids = list(self._by_session.get(session_id, set()))
            targets = [self._conns[i] for i in conn_ids if i in self._conns]

        sent = 0
        failed = 0
        results = []

        for conn in targets:
            try:
                await conn.send_json(payload)
                sent += 1
                if include_metadata:
                    results.append(
                        {
                            "connection_id": conn.meta.connection_id,
                            "client_type": conn.meta.client_type,
                            "status": "sent",
                        }
                    )
            except Exception as e:
                failed += 1
                logger.error(
                    f"Session broadcast failed: {e}",
                    extra={
                        "conn_id": conn.meta.connection_id,
                        "session_id": session_id,
                    },
                )
                if include_metadata:
                    results.append(
                        {
                            "connection_id": conn.meta.connection_id,
                            "client_type": conn.meta.client_type,
                            "status": "failed",
                            "error": str(e),
                        }
                    )

        return {
            "session_id": session_id,
            "sent": sent,
            "failed": failed,
            "total_targets": len(targets),
            "results": results if include_metadata else None,
        }
