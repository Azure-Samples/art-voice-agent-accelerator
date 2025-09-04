"""
V1 Realtime API Endpoints - Enterprise Architecture
===================================================

Enhanced WebSocket endpoints for real-time communication with enterprise features.
Provides backward-compatible endpoints with enhanced observability and orchestrator support.

V1 Architecture Improvements:
- Comprehensive Swagger/OpenAPI documentation
- Advanced OpenTelemetry tracing and observability
- Pluggable orchestrator support for different conversation engines
- Enhanced session management with proper resource cleanup
- Production-ready error handling and recovery
- Clean separation of concerns with focused helper functions

Key V1 Features:
- Dashboard relay with advanced connection tracking
- Browser conversation with STT/TTS streaming
- Legacy compatibility endpoints for seamless migration
- Enhanced audio processing with interruption handling
- Comprehensive session state management
- Production-ready WebSocket handling

WebSocket Flow:
1. Accept connection and validate dependencies
2. Initialize session with proper state management
3. Process streaming audio/text with error handling
4. Route through pluggable orchestrator system
5. Stream responses with TTS and visual feedback
6. Clean up resources on disconnect/error
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Optional, Set
from datetime import datetime

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    HTTPException,
    Request,
    Query,
    status,
)
from fastapi.websockets import WebSocketState
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

# Core application imports
from config import GREETING, ENABLE_AUTH_VALIDATION
from apps.rtagent.backend.src.helpers import check_for_stopwords, receive_and_filter
from src.tools.latency_tool import LatencyTool
from apps.rtagent.backend.src.orchestration.artagent.orchestrator import route_turn
from apps.rtagent.backend.src.ws_helpers.shared_ws import send_tts_audio
from apps.rtagent.backend.src.ws_helpers.envelopes import (
    make_envelope,
    make_status_envelope,
    make_assistant_streaming_envelope,
    make_event_envelope,
)
from src.speech.speech_recognizer import StreamingSpeechRecognizerFromBytes
from src.postcall.push import build_and_flush
from src.stateful.state_managment import MemoManager
from utils.ml_logging import get_logger

# V1 components
from ..dependencies.orchestrator import get_orchestrator
from ..schemas.realtime import (
    RealtimeStatusResponse,
    DashboardConnectionResponse,
    ConversationSessionResponse,
)
from apps.rtagent.backend.src.utils.tracing import log_with_context
from apps.rtagent.backend.src.utils.auth import validate_acs_ws_auth, AuthError

logger = get_logger("api.v1.endpoints.realtime")
tracer = trace.get_tracer(__name__)

router = APIRouter()


@router.get(
    "/status",
    response_model=RealtimeStatusResponse,
    summary="Get Realtime Service Status",
    description="""
    Get the current status of the realtime communication service.
    
    Returns information about:
    - Service availability and health
    - Supported protocols and features
    - Active connection counts
    - WebSocket endpoint configurations
    """,
    tags=["Realtime Status"],
    responses={
        200: {
            "description": "Service status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "available",
                        "websocket_endpoints": {
                            "dashboard_relay": "/api/v1/realtime/dashboard/relay",
                            "conversation": "/api/v1/realtime/conversation",
                        },
                        "features": {
                            "dashboard_broadcasting": True,
                            "conversation_streaming": True,
                            "orchestrator_support": True,
                            "session_management": True,
                        },
                        "active_connections": {
                            "dashboard_clients": 0,
                            "conversation_sessions": 0,
                        },
                        "version": "v1",
                    }
                }
            },
        }
    },
)
async def get_realtime_status(request: Request) -> RealtimeStatusResponse:
    """
    Retrieve comprehensive status and configuration of real-time communication services.

    Provides detailed information about WebSocket endpoint availability, active
    session counts, supported features, and service health. Essential for
    monitoring dashboard functionality and conversation capabilities within
    the voice agent system.

    Args:
        request: FastAPI request object providing access to application state,
                session manager, and connection statistics.

    Returns:
        RealtimeStatusResponse: Complete service status including WebSocket
        endpoints, feature flags, active connection counts, and API version.

    Note:
        This endpoint is designed to always return current service status
        and does not raise exceptions under normal circumstances.
    """
    session_count = await request.app.state.session_manager.get_session_count()

    # Get connection stats from the new manager
    conn_stats = await request.app.state.conn_manager.stats()
    dashboard_clients = conn_stats.get("by_topic", {}).get("dashboard", 0)

    return RealtimeStatusResponse(
        status="available",
        websocket_endpoints={
            "dashboard_relay": "/api/v1/realtime/dashboard/relay",
            "conversation": "/api/v1/realtime/conversation",
        },
        features={
            "dashboard_broadcasting": True,
            "conversation_streaming": True,
            "orchestrator_support": True,
            "session_management": True,
            "audio_interruption": True,
            "precise_routing": True,
            "connection_queuing": True,
        },
        active_connections={
            "dashboard_clients": dashboard_clients,
            "conversation_sessions": session_count,
            "total_connections": conn_stats.get("connections", 0),
        },
        protocols_supported=["WebSocket"],
        version="v1",
    )


@router.websocket("/dashboard/relay")
async def dashboard_relay_endpoint(
    websocket: WebSocket, session_id: Optional[str] = Query(None)
) -> None:
    """
    Production-ready WebSocket endpoint for dashboard relay communication.

    Establishes a persistent WebSocket connection for dashboard clients to
    receive real-time updates and notifications. Handles session filtering,
    connection management, and proper resource cleanup with comprehensive
    error handling and observability.

    Args:
        websocket: WebSocket connection from dashboard client for real-time updates.
        session_id: Optional session ID for filtering dashboard messages to
                   specific conversation sessions.

    Raises:
        WebSocketDisconnect: When dashboard client disconnects from WebSocket.
        Exception: For authentication failures or system errors during connection.

    Note:
        Session ID enables dashboard clients to monitor specific conversation
        sessions while maintaining connection isolation and proper routing.
    """
    client_id = None
    conn_id = None
    try:
        # Generate client ID for logging
        client_id = str(uuid.uuid4())[:8]

        # Log session correlation for debugging
        logger.info(
            f"[BACKEND] Dashboard relay WebSocket connection from frontend with session_id: {session_id}"
        )
        logger.info(f"[BACKEND] Client ID: {client_id} | Session ID: {session_id}")

        with tracer.start_as_current_span(
            "api.v1.realtime.dashboard_relay_connect",
            kind=SpanKind.SERVER,
            attributes={
                "api.version": "v1",
                "realtime.client_id": client_id,
                "realtime.endpoint": "dashboard_relay",
                "network.protocol.name": "websocket",
            },
        ) as connect_span:
            # Clean single-call registration (handles accept + registration)
            conn_id = await websocket.app.state.conn_manager.register(
                websocket,
                client_type="dashboard",
                topics={"dashboard"},
                session_id=session_id,  # 🎯 CRITICAL: Include session ID for proper routing
                accept_already_done=False,  # Let manager handle accept cleanly
            )

            # Track WebSocket connection for session metrics
            if hasattr(websocket.app.state, "session_metrics"):
                await websocket.app.state.session_metrics.increment_connected()

            # Get updated connection stats
            conn_stats = await websocket.app.state.conn_manager.stats()
            dashboard_count = conn_stats.get("by_topic", {}).get("dashboard", 0)

            connect_span.set_attribute("dashboard.clients.total", dashboard_count)
            connect_span.set_status(Status(StatusCode.OK))

            log_with_context(
                logger,
                "info",
                "Dashboard client connected successfully",
                operation="dashboard_connect",
                client_id=client_id,
                conn_id=conn_id,
                total_dashboard_clients=dashboard_count,
                api_version="v1",
            )

        # Process dashboard messages
        await _process_dashboard_messages(websocket, client_id)

    except WebSocketDisconnect as e:
        _log_dashboard_disconnect(e, client_id)
    except Exception as e:
        _log_dashboard_error(e, client_id)
        raise
    finally:
        await _cleanup_dashboard_connection(websocket, client_id, conn_id)


@router.websocket("/conversation")
async def browser_conversation_endpoint(
    websocket: WebSocket,
    session_id: Optional[str] = Query(None),
    orchestrator: Optional[callable] = Depends(get_orchestrator),
) -> None:
    """
    Production-ready WebSocket endpoint for browser-based voice conversations.

    Handles real-time bidirectional audio communication between browser clients
    and the voice agent system. Supports speech-to-text, text-to-speech,
    conversation orchestration, and session persistence with comprehensive
    error handling and resource management.

    Args:
        websocket: WebSocket connection from browser client for voice interaction.
        session_id: Optional session ID for conversation persistence and state
                   management across reconnections.
        orchestrator: Injected conversation orchestrator for processing user
                     interactions and generating responses.

    Raises:
        WebSocketDisconnect: When browser client disconnects normally or abnormally.
        HTTPException: For authentication failures or dependency validation errors.
        Exception: For system errors during conversation processing.

    Note:
        Session ID generation: Uses provided session_id, ACS call-connection-id
        from headers, or generates collision-resistant UUID4 for session isolation.
    """
    memory_manager = None
    conn_id = None

    try:
        # Use provided session_id or generate collision-resistant session ID
        if not session_id:
            if websocket.headers.get("x-ms-call-connection-id"):
                # For ACS calls, use the full call-connection-id (already unique)
                session_id = websocket.headers.get("x-ms-call-connection-id")
            else:
                # For realtime calls, use full UUID4 to prevent collisions
                session_id = str(uuid.uuid4())

        logger.info(
            f"[BACKEND] Conversation WebSocket connection from frontend with session_id: {session_id}"
        )
        logger.info(
            f"[BACKEND] Browser conversation starting with session_id: {session_id}"
        )

        with tracer.start_as_current_span(
            "api.v1.realtime.conversation_connect",
            kind=SpanKind.SERVER,
            attributes={
                "api.version": "v1",
                "realtime.session_id": session_id,
                "realtime.endpoint": "conversation",
                "network.protocol.name": "websocket",
                "orchestrator.name": getattr(orchestrator, "name", "unknown")
                if orchestrator
                else "default",
            },
        ) as connect_span:
            # Clean single-call registration with optional auth
            conn_id = await websocket.app.state.conn_manager.register(
                websocket,
                client_type="conversation",
                session_id=session_id,
                topics={"conversation"},
                accept_already_done=False,  # Let manager handle accept cleanly
            )

            # Store conn_id on websocket state for consistent access
            websocket.state.conn_id = conn_id

            # Initialize conversation session
            memory_manager = await _initialize_conversation_session(
                websocket, session_id, conn_id, orchestrator
            )

            # Register session thread-safely
            await websocket.app.state.session_manager.add_session(
                session_id, memory_manager, websocket
            )

            # Track WebSocket connection for session metrics
            if hasattr(websocket.app.state, "session_metrics"):
                await websocket.app.state.session_metrics.increment_connected()

            session_count = (
                await websocket.app.state.session_manager.get_session_count()
            )
            connect_span.set_attribute("conversation.sessions.total", session_count)
            connect_span.set_status(Status(StatusCode.OK))

            log_with_context(
                logger,
                "info",
                "Conversation session initialized successfully",
                operation="conversation_connect",
                session_id=session_id,
                conn_id=conn_id,
                total_sessions=session_count,
                api_version="v1",
            )

        # Process conversation messages
        await _process_conversation_messages(
            websocket, session_id, memory_manager, orchestrator, conn_id
        )

    except WebSocketDisconnect as e:
        _log_conversation_disconnect(e, session_id)
    except Exception as e:
        _log_conversation_error(e, session_id)
        raise
    finally:
        await _cleanup_conversation_session(
            websocket, session_id, memory_manager, conn_id
        )


# ============================================================================
# V1 Architecture Helper Functions
# ============================================================================


async def _initialize_conversation_session(
    websocket: WebSocket,
    session_id: str,
    conn_id: str,
    orchestrator: Optional[callable],
) -> MemoManager:
    """Initialize conversation session with consolidated state management.

    :param websocket: WebSocket connection for the conversation
    :param session_id: Unique identifier for the conversation session
    :param orchestrator: Optional orchestrator for conversation routing
    :return: Initialized MemoManager instance for conversation state
    :raises Exception: If session initialization fails
    """
    redis_mgr = websocket.app.state.redis
    memory_manager = MemoManager.from_redis(session_id, redis_mgr)

    # Acquire per-connection TTS synthesizer from pool
    tts_client = await websocket.app.state.tts_pool.acquire()
    logger.info(f"Acquired TTS synthesizer from pool for session {session_id}")

    # Create latency tool for this session
    latency_tool = LatencyTool(memory_manager)

    # Track background orchestration tasks for proper cleanup
    orchestration_tasks = set()

    # Set up WebSocket state for orchestrator compatibility
    websocket.state.cm = memory_manager
    websocket.state.session_id = session_id
    websocket.state.tts_client = tts_client
    websocket.state.lt = latency_tool  # ← KEY FIX: Orchestrator expects this
    websocket.state.is_synthesizing = False
    websocket.state.user_buffer = ""
    websocket.state.orchestration_tasks = orchestration_tasks  # Track background tasks
    # Capture event loop for thread-safe scheduling from STT callbacks
    try:
        websocket.state._loop = asyncio.get_running_loop()
    except RuntimeError:
        websocket.state._loop = None

    # Set up WebSocket state through connection manager metadata (for compatibility)
    conn_manager = websocket.app.state.conn_manager
    connection = conn_manager._conns.get(conn_id)
    if connection:
        connection.meta.handler = {
            "cm": memory_manager,
            "session_id": session_id,
            "tts_client": tts_client,
            "lt": latency_tool,
            "is_synthesizing": False,
            "user_buffer": "",
        }

    # Helper function to access connection metadata
    def get_metadata(key: str, default=None):
        # Use connection metadata as single source of truth
        if connection and connection.meta.handler:
            return connection.meta.handler.get(key, default)
        return default

    def set_metadata(key: str, value):
        # Use connection metadata as single source of truth
        if connection and connection.meta.handler:
            connection.meta.handler[key] = value

    # Send greeting message using new envelope format
    greeting_envelope = make_status_envelope(
        GREETING,
        sender="System",
        topic="session",
        session_id=session_id,
    )
    await websocket.app.state.conn_manager.send_to_connection(
        conn_id, greeting_envelope
    )

    # Add greeting to conversation history
    auth_agent = websocket.app.state.auth_agent
    memory_manager.append_to_history(auth_agent.name, "assistant", GREETING)

    # Send TTS audio greeting
    latency_tool = get_metadata("lt")
    await send_tts_audio(GREETING, websocket, latency_tool=latency_tool)

    # Persist initial state to Redis
    await memory_manager.persist_to_redis_async(redis_mgr)

    # Set up STT callbacks
    def on_partial(txt: str, lang: str, speaker_id: str):
        logger.info(f"User (partial) in {lang}: {txt}")
        try:
            # Check both synthesis flag and session audio state for barge-in
            is_synthesizing = get_metadata("is_synthesizing", False)
            audio_playing = get_metadata("audio_playing", False)

            if is_synthesizing or audio_playing:
                # Interrupt TTS synthesizer immediately
                tts_client = get_metadata("tts_client")
                if tts_client:
                    tts_client.stop_speaking()

                # Clear both synthesis flag and audio state
                set_metadata("is_synthesizing", False)
                set_metadata("audio_playing", False)
                set_metadata("tts_cancel_requested", True)

                # Notify UI to flush any buffered audio
                cancel_msg = {
                    "type": "control",
                    "action": "tts_cancelled",
                    "reason": "barge_in",
                    "at": "partial",
                    "session_id": session_id,
                }
                loop = getattr(websocket.state, "_loop", None)
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(
                        asyncio.create_task,
                        websocket.app.state.conn_manager.send_to_connection(
                            conn_id, cancel_msg
                        ),
                    )
                else:
                    # Best-effort fallback
                    asyncio.create_task(
                        websocket.app.state.conn_manager.send_to_connection(
                            conn_id, cancel_msg
                        )
                    )
        except Exception as e:
            logger.debug(f"Failed to dispatch UI cancel control: {e}")

    def on_final(txt: str, lang: str):
        logger.info(f"User (final) in {lang}: {txt}")
        current_buffer = get_metadata("user_buffer", "")
        set_metadata("user_buffer", current_buffer + txt.strip() + "\n")

    # Acquire per‑connection speech recognizer from pool
    stt_client = await websocket.app.state.stt_pool.acquire()
    set_metadata("stt_client", stt_client)
    stt_client.set_partial_result_callback(on_partial)
    stt_client.set_final_result_callback(on_final)
    stt_client.start()

    # Allocate dedicated TTS client for this session
    if hasattr(websocket.app.state, "dedicated_tts_manager"):
        try:
            (
                tts_client,
                client_tier,
            ) = await websocket.app.state.dedicated_tts_manager.get_dedicated_client(
                session_id
            )
            set_metadata("tts_client", tts_client)
            set_metadata("tts_client_tier", client_tier)

            # Store session_id on WebSocket state for shared_ws access
            websocket.state.session_id = session_id

            logger.info(
                f"Allocated dedicated TTS client for session {session_id} (tier={client_tier.value})"
            )
        except Exception as e:
            logger.warning(
                f"Failed to allocate dedicated TTS client for session {session_id}: {e}"
            )

    logger.info(f"STT recognizer started for session {session_id}")
    return memory_manager


async def _process_dashboard_messages(websocket: WebSocket, client_id: str) -> None:
    """Process incoming dashboard relay messages.

    :param websocket: WebSocket connection for dashboard client
    :param client_id: Unique identifier for the dashboard client
    :return: None
    :raises WebSocketDisconnect: When client disconnects normally
    :raises Exception: For any other errors during message processing
    """
    with tracer.start_as_current_span(
        "api.v1.realtime.process_dashboard_messages",
        attributes={"client_id": client_id},
    ):
        try:
            while (
                websocket.client_state == WebSocketState.CONNECTED
                and websocket.application_state == WebSocketState.CONNECTED
            ):
                # Keep connection alive and process any ping/pong messages
                await websocket.receive_text()

        except WebSocketDisconnect:
            # Normal disconnect - handled in the calling function
            raise
        except Exception as e:
            logger.error(
                f"Error processing dashboard messages for client {client_id}: {e}"
            )
            raise


async def _process_conversation_messages(
    websocket: WebSocket,
    session_id: str,
    memory_manager: MemoManager,
    orchestrator: Optional[callable],
    conn_id: str,
) -> None:
    """Process incoming conversation messages with enhanced error handling.

    :param websocket: WebSocket connection for conversation client
    :param session_id: Unique identifier for the conversation session
    :param memory_manager: MemoManager instance for conversation state
    :param orchestrator: Optional orchestrator for conversation routing
    :return: None
    :raises WebSocketDisconnect: When client disconnects normally
    :raises Exception: For any other errors during message processing
    """
    with tracer.start_as_current_span(
        "api.v1.realtime.process_conversation_messages",
        attributes={"session_id": session_id},
    ) as span:
        try:
            # Get connection manager for this session
            conn_manager = websocket.app.state.conn_manager
            connection = conn_manager._conns.get(conn_id)

            # Helper function to access connection metadata
            def get_metadata(key: str, default=None):
                if connection and connection.meta.handler:
                    return connection.meta.handler.get(key, default)
                return default

            def set_metadata(key: str, value):
                if connection and connection.meta.handler:
                    connection.meta.handler[key] = value

            message_count = 0
            while (
                websocket.client_state == WebSocketState.CONNECTED
                and websocket.application_state == WebSocketState.CONNECTED
            ):
                msg = await websocket.receive()
                message_count += 1

                # Handle audio bytes
                if (
                    msg.get("type") == "websocket.receive"
                    and msg.get("bytes") is not None
                ):
                    stt_client = get_metadata("stt_client")
                    if stt_client:
                        stt_client.write_bytes(msg["bytes"])

                # Process accumulated user buffer (moved outside audio handling to prevent duplication)
                user_buffer = get_metadata("user_buffer", "")
                if user_buffer.strip():
                    prompt = user_buffer.strip()
                    set_metadata("user_buffer", "")

                    # Send user message to all connections in the session using session-isolated broadcasting
                    user_envelope = make_envelope(
                        etype="event",
                        sender="User",
                        payload={"sender": "User", "message": prompt},
                        topic="session",
                        session_id=session_id,
                    )
                    await websocket.app.state.conn_manager.broadcast_session(
                        session_id, user_envelope
                    )

                    # Check for stopwords
                    if check_for_stopwords(prompt):
                        goodbye = "Thank you for using our service. Goodbye."
                        goodbye_envelope = make_envelope(
                            etype="exit",
                            sender="System",
                            payload={"type": "exit", "message": goodbye},
                            topic="session",
                            session_id=session_id,
                        )
                        await websocket.app.state.conn_manager.broadcast_session(
                            session_id, goodbye_envelope
                        )
                        latency_tool = get_metadata("lt")
                        await send_tts_audio(
                            goodbye, websocket, latency_tool=latency_tool
                        )
                        break

                    # Process orchestration in background for non-blocking response
                    # This prevents blocking the WebSocket receive loop, allowing true parallelism
                    async def run_orchestration():
                        try:
                            await route_turn(
                                memory_manager, prompt, websocket, is_acs=False
                            )
                        except Exception as e:
                            logger.error(
                                f"[PERF] Orchestration task failed for session {session_id}: {e}"
                            )
                        finally:
                            # Clean up completed task from tracking set
                            orchestration_tasks = getattr(
                                websocket.state, "orchestration_tasks", set()
                            )
                            orchestration_tasks.discard(asyncio.current_task())

                    orchestration_task = asyncio.create_task(run_orchestration())

                    # Track the task for proper cleanup
                    orchestration_tasks = getattr(
                        websocket.state, "orchestration_tasks", set()
                    )
                    orchestration_tasks.add(orchestration_task)

                    logger.debug(
                        f"[PERF] Started parallel orchestration task for session {session_id} (active tasks: {len(orchestration_tasks)})"
                    )

                # Handle disconnect
                elif msg.get("type") == "websocket.disconnect":
                    break

            span.set_attribute("messages.processed", message_count)
            span.set_status(Status(StatusCode.OK))

        except WebSocketDisconnect:
            span.set_status(Status(StatusCode.OK, "Normal disconnect"))
            raise
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, f"Message processing error: {e}"))
            logger.error(
                f"Error processing conversation messages for session {session_id}: {e}"
            )
            raise


def _log_dashboard_disconnect(e: WebSocketDisconnect, client_id: Optional[str]) -> None:
    """Log dashboard client disconnection.

    :param e: WebSocketDisconnect exception containing disconnect details
    :param client_id: Optional unique identifier for the dashboard client
    :return: None
    :raises: None
    """
    if e.code == 1000:
        log_with_context(
            logger,
            "info",
            "Dashboard client disconnected normally",
            operation="dashboard_disconnect",
            client_id=client_id,
            disconnect_code=e.code,
            api_version="v1",
        )
    else:
        log_with_context(
            logger,
            "warning",
            "Dashboard client disconnected abnormally",
            operation="dashboard_disconnect",
            client_id=client_id,
            disconnect_code=e.code,
            reason=e.reason,
            api_version="v1",
        )


def _log_dashboard_error(e: Exception, client_id: Optional[str]) -> None:
    """Log dashboard client errors.

    :param e: Exception that occurred during dashboard operation
    :param client_id: Optional unique identifier for the dashboard client
    :return: None
    :raises: None
    """
    log_with_context(
        logger,
        "error",
        "Dashboard client error",
        operation="dashboard_error",
        client_id=client_id,
        error=str(e),
        error_type=type(e).__name__,
        api_version="v1",
    )


def _log_conversation_disconnect(
    e: WebSocketDisconnect, session_id: Optional[str]
) -> None:
    """Log conversation session disconnection.

    :param e: WebSocketDisconnect exception containing disconnect details
    :param session_id: Optional unique identifier for the conversation session
    :return: None
    :raises: None
    """
    if e.code == 1000:
        log_with_context(
            logger,
            "info",
            "Conversation session ended normally",
            operation="conversation_disconnect",
            session_id=session_id,
            disconnect_code=e.code,
            api_version="v1",
        )
    else:
        log_with_context(
            logger,
            "warning",
            "Conversation session ended abnormally",
            operation="conversation_disconnect",
            session_id=session_id,
            disconnect_code=e.code,
            reason=e.reason,
            api_version="v1",
        )


def _log_conversation_error(e: Exception, session_id: Optional[str]) -> None:
    """Log conversation session errors.

    :param e: Exception that occurred during conversation operation
    :param session_id: Optional unique identifier for the conversation session
    :return: None
    :raises: None
    """
    log_with_context(
        logger,
        "error",
        "Conversation session error",
        operation="conversation_error",
        session_id=session_id,
        error=str(e),
        error_type=type(e).__name__,
        api_version="v1",
    )


async def _cleanup_dashboard_connection(
    websocket: WebSocket, client_id: Optional[str], conn_id: Optional[str]
) -> None:
    """Clean up dashboard connection resources.

    :param websocket: WebSocket connection to clean up
    :param client_id: Optional unique identifier for the dashboard client
    :param conn_id: Optional connection manager ID
    :return: None
    :raises Exception: If cleanup operations fail (logged but not re-raised)
    """
    with tracer.start_as_current_span(
        "api.v1.realtime.cleanup_dashboard",
        attributes={"client_id": client_id, "conn_id": conn_id},
    ) as span:
        try:
            # Unregister from connection manager
            if conn_id:
                await websocket.app.state.conn_manager.unregister(conn_id)
                logger.info(f"Dashboard connection {conn_id} unregistered from manager")

            # Track WebSocket disconnection for session metrics
            if hasattr(websocket.app.state, "session_metrics"):
                await websocket.app.state.session_metrics.increment_disconnected()

            # Close WebSocket if still connected
            if (
                websocket.client_state == WebSocketState.CONNECTED
                and websocket.application_state == WebSocketState.CONNECTED
            ):
                await websocket.close()

            span.set_status(Status(StatusCode.OK))
            log_with_context(
                logger,
                "info",
                "Dashboard connection cleanup complete",
                operation="dashboard_cleanup",
                client_id=client_id,
                conn_id=conn_id,
                api_version="v1",
            )

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, f"Cleanup error: {e}"))
            logger.error(f"Error during dashboard cleanup: {e}")


async def _cleanup_conversation_session(
    websocket: WebSocket,
    session_id: Optional[str],
    memory_manager: Optional[MemoManager],
    conn_id: Optional[str],
) -> None:
    """Clean up conversation session resources.

    :param websocket: WebSocket connection to clean up
    :param session_id: Optional unique identifier for the conversation session
    :param memory_manager: Optional MemoManager instance to persist
    :param conn_id: Optional connection manager ID
    :return: None
    :raises Exception: If cleanup operations fail (logged but not re-raised)
    """
    with tracer.start_as_current_span(
        "api.v1.realtime.cleanup_conversation",
        attributes={"session_id": session_id, "conn_id": conn_id},
    ) as span:
        try:
            # Cancel background orchestration tasks to prevent resource leaks
            orchestration_tasks = getattr(websocket.state, "orchestration_tasks", set())
            if orchestration_tasks:
                logger.info(
                    f"[PERF] Cancelling {len(orchestration_tasks)} background orchestration tasks for session {session_id}"
                )
                for task in orchestration_tasks.copy():
                    if not task.done():
                        task.cancel()
                        try:
                            await asyncio.wait_for(task, timeout=1.0)
                        except (asyncio.CancelledError, asyncio.TimeoutError):
                            pass  # Expected for cancelled tasks
                        except Exception as e:
                            logger.warning(
                                f"[PERF] Error during task cancellation: {e}"
                            )
                orchestration_tasks.clear()
                logger.debug(
                    f"[PERF] Background task cleanup complete for session {session_id}"
                )

            # Clean up session resources directly through connection manager
            conn_manager = websocket.app.state.conn_manager
            connection = conn_manager._conns.get(conn_id)

            if connection and connection.meta.handler:
                # Clean up TTS client
                tts_client = connection.meta.handler.get("tts_client")
                if tts_client and hasattr(websocket.app.state, "tts_pool"):
                    try:
                        tts_client.stop_speaking()
                        await websocket.app.state.tts_pool.release(tts_client)
                        logger.info("Released TTS client during cleanup")
                    except Exception as e:
                        logger.error(f"Error releasing TTS client: {e}")

                # Release dedicated TTS client
                if hasattr(websocket.app.state, "dedicated_tts_manager") and session_id:
                    try:
                        released = await websocket.app.state.dedicated_tts_manager.release_session_client(
                            session_id
                        )
                        if released:
                            logger.info(
                                f"Released dedicated TTS client for session {session_id}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error releasing dedicated TTS client for session {session_id}: {e}"
                        )

                #  Release session-specific AOAI client
                if session_id:
                    try:
                        from src.pools.aoai_pool import release_session_client

                        await release_session_client(session_id)
                        logger.info(
                            f"Released dedicated AOAI client for session {session_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Error releasing AOAI client for session {session_id}: {e}"
                        )

                # Clean up STT client
                stt_client = connection.meta.handler.get("stt_client")
                if stt_client and hasattr(websocket.app.state, "stt_pool"):
                    try:
                        stt_client.stop()
                        await websocket.app.state.stt_pool.release(stt_client)
                        logger.info("Released STT client during cleanup")
                    except Exception as e:
                        logger.error(f"Error releasing STT client: {e}")

                # Clean up any other tracked tasks
                tts_tasks = connection.meta.handler.get("tts_tasks")
                if tts_tasks:
                    for task in list(tts_tasks):
                        if not task.done():
                            task.cancel()
                            logger.debug("Cancelled TTS task during cleanup")

                # Clean up latency timers on session disconnect
                latency_tool = connection.meta.handler.get("latency_tool")
                if latency_tool and hasattr(latency_tool, "cleanup_timers"):
                    try:
                        latency_tool.cleanup_timers()
                        logger.debug(
                            "Cleaned up latency timers during realtime cleanup"
                        )
                    except Exception as e:
                        logger.error(f"Error cleaning up latency timers: {e}")

            logger.info(f"Session cleanup complete for {conn_id}")

            # Unregister from connection manager (this also cleans up handler if attached)
            if conn_id:
                await websocket.app.state.conn_manager.unregister(conn_id)
                logger.info(
                    f"Conversation connection {conn_id} unregistered from manager"
                )

            # Remove from session registry thread-safely
            if session_id:
                removed = await websocket.app.state.session_manager.remove_session(
                    session_id
                )
                if removed:
                    remaining_count = (
                        await websocket.app.state.session_manager.get_session_count()
                    )
                    logger.info(
                        f"Conversation session {session_id} removed. Active sessions: {remaining_count}"
                    )

            # Track WebSocket disconnection for session metrics
            if hasattr(websocket.app.state, "session_metrics"):
                await websocket.app.state.session_metrics.increment_disconnected()

            # Close WebSocket if still connected
            if (
                websocket.client_state == WebSocketState.CONNECTED
                and websocket.application_state == WebSocketState.CONNECTED
            ):
                await websocket.close()

            # Persist analytics if possible
            if memory_manager and hasattr(websocket.app.state, "cosmos"):
                try:
                    build_and_flush(memory_manager, websocket.app.state.cosmos)
                except Exception as e:
                    logger.error(f"Error persisting analytics: {e}", exc_info=True)

            span.set_status(Status(StatusCode.OK))
            log_with_context(
                logger,
                "info",
                "Conversation session cleanup complete",
                operation="conversation_cleanup",
                session_id=session_id,
                conn_id=conn_id,
                api_version="v1",
            )

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, f"Cleanup error: {e}"))
            logger.error(f"Error during conversation cleanup: {e}")
