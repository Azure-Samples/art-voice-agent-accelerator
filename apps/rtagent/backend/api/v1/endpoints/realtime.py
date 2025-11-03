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

import array
import asyncio
import json
import math
import time
import uuid
from typing import Any, Dict, Optional
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
from apps.rtagent.backend.src.orchestration.artagent.cm_utils import (
    cm_get,
    cm_set,
)
from apps.rtagent.backend.src.ws_helpers.shared_ws import (
    _get_connection_metadata,
    _set_connection_metadata,
    send_session_envelope,
    send_tts_audio,
)
from apps.rtagent.backend.src.ws_helpers.barge_in import BargeInController
from apps.rtagent.backend.src.ws_helpers.envelopes import (
    make_envelope,
    make_status_envelope,
    make_assistant_streaming_envelope,
    make_event_envelope,
)
from src.speech.speech_recognizer import StreamingSpeechRecognizerFromBytes
from src.postcall.push import build_and_flush
from src.stateful.state_managment import MemoManager
from src.pools.session_manager import SessionContext
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

_STATE_SENTINEL = object()

router = APIRouter()




def _pcm16le_rms(audio_bytes: bytes) -> float:
    if not audio_bytes:
        return 0.0

    sample_count = len(audio_bytes) // 2
    if sample_count <= 0:
        return 0.0

    samples = array.array("h")
    try:
        samples.frombytes(audio_bytes[: sample_count * 2])
    except Exception:
        return 0.0

    if not samples:
        return 0.0

    accum = 0.0
    for value in samples:
        accum += float(value * value)

    return math.sqrt(accum / len(samples))

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
                            "audio_interruption": True,
                            "precise_routing": True,
                            "connection_queuing": True,
                        },
                        "active_connections": {
                            "dashboard_clients": 0,
                            "conversation_sessions": 0,
                            "total_connections": 0,
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
            f"[{session_id}] Conversation WebSocket connection established"
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
            memory_manager, session_metadata = await _initialize_conversation_session(
                websocket, session_id, conn_id, orchestrator
            )

            # Register session thread-safely
            await websocket.app.state.session_manager.add_session(
                session_id, memory_manager, websocket, metadata=session_metadata
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
) -> tuple[MemoManager, Dict[str, Any]]:
    """Initialize conversation session with consolidated state and metadata.

    :param websocket: WebSocket connection for the conversation
    :param session_id: Unique identifier for the conversation session
    :param orchestrator: Optional orchestrator for conversation routing
    :return: Tuple of (MemoManager, metadata dict) for downstream registration
    :raises Exception: If session initialization fails
    """
    redis_mgr = websocket.app.state.redis
    memory_manager = MemoManager.from_redis(session_id, redis_mgr)

    # Acquire per-connection TTS synthesizer from pool
    tts_pool = websocket.app.state.tts_pool
    try:
        (
            tts_client,
            tts_tier,
        ) = await tts_pool.acquire_for_session(session_id)
    except TimeoutError as exc:
        pool_status = tts_pool.snapshot()
        logger.error(
            "[%s] TTS pool acquire timeout: %s",
            session_id,
            pool_status,
        )
        log_with_context(
            logger,
            "error",
            "TTS pool acquire timeout",
            operation="tts_acquire_timeout",
            session_id=session_id,
            pool_status=json.dumps(pool_status),
        )
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(
                    code=1013, reason="TTS capacity temporarily unavailable"
                )
            except Exception:
                pass
        raise WebSocketDisconnect(code=1013) from exc

    logger.info(
        "[%s] Acquired TTS synthesizer from pool (tier=%s)",
        session_id,
        getattr(tts_tier, "value", "unknown"),
    )

    # Create latency tool for this session
    latency_tool = LatencyTool(memory_manager)

    # Track background orchestration tasks for proper cleanup
    orchestration_tasks = set()

    # Shared cancellation signal for TTS barge-in handling
    tts_cancel_event = asyncio.Event()

    # Set up WebSocket state for orchestrator compatibility
    websocket.state.cm = memory_manager
    websocket.state.session_id = session_id
    websocket.state.tts_client = tts_client
    websocket.state.lt = latency_tool  # ← KEY FIX: Orchestrator expects this
    websocket.state.is_synthesizing = False
    websocket.state.audio_playing = False
    websocket.state.tts_cancel_requested = False
    greeting_sent = memory_manager.get_value_from_corememory("greeting_sent", False)
    websocket.state.greeting_sent = greeting_sent
    websocket.state.user_buffer = ""
    websocket.state.orchestration_tasks = orchestration_tasks  # Track background tasks
    websocket.state.tts_cancel_event = tts_cancel_event
    # Capture event loop for thread-safe scheduling from STT callbacks
    try:
        websocket.state._loop = asyncio.get_running_loop()
    except RuntimeError:
        websocket.state._loop = None

    session_context = getattr(websocket.state, "session_context", None)
    if not isinstance(session_context, SessionContext) or session_context.session_id != session_id:
        session_context = SessionContext(
            session_id=session_id,
            memory_manager=memory_manager,
            websocket=websocket,
        )
        websocket.state.session_context = session_context

    initial_metadata = {
        "cm": memory_manager,
        "session_id": session_id,
        "tts_client": tts_client,
        "lt": latency_tool,
        "is_synthesizing": False,
        "user_buffer": "",
        "tts_cancel_event": tts_cancel_event,
        "audio_playing": False,
        "tts_cancel_requested": False,
        "greeting_sent": greeting_sent,
        "last_tts_start_ts": 0.0,
        "last_tts_end_ts": 0.0,
    }

    for key, value in initial_metadata.items():
        session_context.set_metadata_nowait(key, value)
        setattr(websocket.state, key, value)

    conn_manager = websocket.app.state.conn_manager
    connection = conn_manager._conns.get(conn_id)
    if connection:
        handler = connection.meta.handler
        if handler is None:
            connection.meta.handler = dict(initial_metadata)
        elif isinstance(handler, dict):
            handler.update(initial_metadata)
        else:
            for key, value in initial_metadata.items():
                setattr(handler, key, value)

    def get_metadata(key: str, default=None):
        return _get_connection_metadata(websocket, key, default)

    def set_metadata(key: str, value):
        if not _set_connection_metadata(websocket, key, value):
            setattr(websocket.state, key, value)

    def set_metadata_threadsafe(key: str, value):
        loop = getattr(websocket.state, "_loop", None)
        if loop and loop.is_running():
            loop.call_soon_threadsafe(set_metadata, key, value)
        else:
            set_metadata(key, value)

    def signal_tts_cancel() -> None:
        cancel_event = get_metadata("tts_cancel_event")
        if not cancel_event:
            return

        loop = getattr(websocket.state, "_loop", None)
        if loop and loop.is_running():
            loop.call_soon_threadsafe(cancel_event.set)
            return

        try:
            cancel_event.set()
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "[%s] Unable to signal TTS cancel event immediately: %s",
                session_id,
                exc,
            )

    barge_in_controller = BargeInController(
        websocket=websocket,
        session_id=session_id,
        conn_id=conn_id,
        get_metadata=get_metadata,
        set_metadata=set_metadata,
        signal_tts_cancel=signal_tts_cancel,
        logger=logger,
    )
    websocket.state.barge_in_controller = barge_in_controller
    initial_metadata.update(
        {
            "request_barge_in": barge_in_controller.request,
            "last_barge_in_ts": 0.0,
            "barge_in_inflight": False,
            "last_barge_in_trigger": None,
        }
    )
    set_metadata("request_barge_in", barge_in_controller.request)
    set_metadata("last_barge_in_ts", 0.0)
    set_metadata("barge_in_inflight", False)
    set_metadata("last_barge_in_trigger", None)

    if not greeting_sent:
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

        # Persist greeting state
        set_metadata("greeting_sent", True)
        cm_set(memory_manager, greeting_sent=True)
        greeting_sent = True
        redis_mgr = websocket.app.state.redis
        try:
            await memory_manager.persist_to_redis_async(redis_mgr)
        except Exception as persist_exc:  # noqa: BLE001
            logger.warning(
                "[%s] Failed to persist greeting_sent flag: %s",
                session_id,
                persist_exc,
            )
    else:
        active_agent = cm_get(memory_manager, "active_agent", None)
        active_agent_voice = cm_get(memory_manager, "active_agent_voice", None)
        if isinstance(active_agent_voice, dict):
            active_voice_name = active_agent_voice.get("voice")
        else:
            active_voice_name = active_agent_voice

        resume_text = (
            f"Specialist \"{active_agent}\" is ready to continue assisting you."
            if active_agent
            else "Session resumed with your previous assistant."
        )
        latency_tool = get_metadata("lt")
        await send_tts_audio(
            resume_text,
            websocket,
            latency_tool=latency_tool,
            voice_name=active_voice_name,
        )
        resume_envelope = make_status_envelope(
            resume_text,
            sender=active_agent or "System",
            topic="session",
            session_id=session_id,
        )
        await websocket.app.state.conn_manager.send_to_connection(
            conn_id, resume_envelope
        )

    # Persist initial state to Redis
    await memory_manager.persist_to_redis_async(redis_mgr)

    # Set up STT callbacks
    def on_partial(txt: str, lang: str, speaker_id: str):
        if not txt or not txt.strip():
            return
        txt = txt.strip()
        logger.info(f"[{session_id}] User (partial) in {lang}: {txt}")

        partial_seq = (get_metadata("stt_partial_seq", 0) or 0) + 1
        set_metadata_threadsafe("stt_partial_seq", partial_seq)

        partial_payload = {
            "type": "streaming",
            "streaming_type": "stt_partial",
            "content": txt,
            "language": lang,
            "speaker_id": speaker_id,
            "session_id": session_id,
            "is_final": False,
            "sequence": partial_seq,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        partial_envelope = make_event_envelope(
            event_type="stt_partial",
            event_data=partial_payload,
            sender="STT",
            topic="session",
            session_id=session_id,
        )

        conn_manager = getattr(websocket.app.state, "conn_manager", None)
        loop = getattr(websocket.state, "_loop", None)
        if conn_manager:
            try:
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        conn_manager.send_to_connection(conn_id, partial_envelope),
                        loop,
                    )
                else:
                    logger.debug(
                        "[%s] Unable to forward partial transcript; event loop unavailable",
                        session_id,
                    )
            except Exception as send_exc:  # noqa: BLE001
                logger.debug(
                    "[%s] Failed to forward partial transcript: %s",
                    session_id,
                    send_exc,
                )
        try:
            now = time.monotonic()
            is_synth = get_metadata("is_synthesizing", False)
            audio_playing = get_metadata("audio_playing", False)
            cancel_requested = get_metadata("tts_cancel_requested", False)
            last_tts_start = get_metadata("last_tts_start_ts", 0.0) or 0.0
            last_tts_end = get_metadata("last_tts_end_ts", 0.0) or 0.0

            recent_tts = False
            if last_tts_start:
                within_active_window = (now - last_tts_start) <= 1.2
                no_recorded_end = last_tts_end <= last_tts_start
                ended_recently = last_tts_end and (now - last_tts_end) <= 0.25
                recent_tts = within_active_window and (no_recorded_end or ended_recently)

            if is_synth or audio_playing or recent_tts:
                signal_tts_cancel()

                set_metadata_threadsafe("tts_cancel_requested", True)
                set_metadata_threadsafe("audio_playing", False)
                set_metadata_threadsafe("is_synthesizing", False)
            elif cancel_requested:
                request_cancel = get_metadata("request_barge_in")
                set_metadata_threadsafe("tts_cancel_requested", False)
                
            if callable(request_cancel):
                request_cancel("stt_partial", "partial")
            else:
                # Fall back to direct barge-in if helper is unavailable.
                loop = getattr(websocket.state, "_loop", None)
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(
                        asyncio.create_task,
                        _perform_barge_in("stt_partial", "partial"),
                    )
                else:
                    asyncio.create_task(
                        _perform_barge_in("stt_partial", "partial")
                    )
        except Exception as e:
            logger.debug(f"Failed to dispatch barge-in request from partial: {e}")

    def on_cancel(evt) -> None:
        try:
            details = getattr(evt.result, "cancellation_details", None)
            reason = getattr(details, "reason", None) if details else None
            error_details = getattr(details, "error_details", None) if details else None
            logger.warning(
                "[%s] STT cancellation received (reason=%s, error=%s)",
                session_id,
                reason,
                error_details,
            )
        except Exception as cancel_exc:  # noqa: BLE001
            logger.warning(
                "[%s] STT cancellation event could not be parsed: %s",
                session_id,
                cancel_exc,
            )

    def on_final(txt: str, lang: str, speaker_id: Optional[str] = None):
        logger.info(f"[{session_id}] User {speaker_id} (final) in {lang}: {txt}")
        current_buffer = get_metadata("user_buffer", "")
        set_metadata("user_buffer", current_buffer + txt.strip() + "\n")

    # Acquire per-connection speech recognizer from pool
    stt_pool = websocket.app.state.stt_pool
    try:
        (
            stt_client,
            stt_tier,
        ) = await stt_pool.acquire_for_session(session_id)
    except TimeoutError as exc:
        pool_status = stt_pool.snapshot()
        logger.error(
            "[%s] STT pool acquire timeout: %s",
            session_id,
            pool_status,
        )
        log_with_context(
            logger,
            "error",
            "STT pool acquire timeout",
            operation="stt_acquire_timeout",
            session_id=session_id,
            pool_status=json.dumps(pool_status),
        )
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(
                    code=1013, reason="STT capacity temporarily unavailable"
                )
            except Exception:
                pass
        raise WebSocketDisconnect(code=1013) from exc

    set_metadata("stt_client", stt_client)
    try:
        stt_client.set_call_connection_id(session_id)
    except Exception as set_conn_exc:
        logger.debug(
            "[%s] Unable to attach call_connection_id to STT client: %s",
            session_id,
            set_conn_exc,
        )
    stt_client.set_partial_result_callback(on_partial)
    stt_client.set_final_result_callback(on_final)
    stt_client.set_cancel_callback(on_cancel)
    stt_client.start()

    # Persist the already-acquired TTS client into metadata
    set_metadata("tts_client", tts_client)
    logger.info(
        "Allocated TTS client for session %s (tier=%s)",
        session_id,
        getattr(tts_tier, "value", "unknown"),
    )

    logger.info(
        "STT recognizer started for session %s (tier=%s)",
        session_id,
        getattr(stt_tier, "value", "unknown"),
    )
    return memory_manager, initial_metadata


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
            session_context = getattr(websocket.state, "session_context", None)

            def get_metadata(key: str, default=None):
                if session_context:
                    value = session_context.get_metadata_nowait(key, _STATE_SENTINEL)
                    if value is not _STATE_SENTINEL:
                        return value
                return _get_connection_metadata(websocket, key, default)

            def set_metadata(key: str, value):
                if session_context:
                    session_context.set_metadata_nowait(key, value)
                if not _set_connection_metadata(websocket, key, value):
                    setattr(websocket.state, key, value)

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
                    audio_bytes = msg["bytes"]
                    first_audio_logged = get_metadata("_audio_first_logged", False)
                    if not first_audio_logged:
                        logger.info(
                            "[%s] Received initial audio frame (%s bytes)",
                            session_id,
                            len(audio_bytes),
                        )
                        set_metadata("_audio_first_logged", True)

                    stt_client = get_metadata("stt_client")
                    if stt_client:
                        is_synth = get_metadata("is_synthesizing", False)
                        audio_playing = get_metadata("audio_playing", False)
                        cancel_requested = get_metadata("tts_cancel_requested", False)

                        if cancel_requested and not (is_synth or audio_playing):
                            set_metadata("tts_cancel_requested", False)

                        if getattr(stt_client, "push_stream", None) is None:
                            logger.warning(
                                "[%s] STT push_stream not ready; dropping audio frame",
                                session_id,
                            )
                        try:
                            stt_client.write_bytes(audio_bytes)
                        except Exception as write_exc:  # noqa: BLE001
                            logger.error(
                                "[%s] Failed to write audio to recognizer: %s",
                                session_id,
                                write_exc,
                            )

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
                            error_payload = {
                                "type": "orchestration_error",
                                "message": "Conversation processing failed.",
                                "details": str(e),
                                "session_id": session_id,
                                "timestamp": datetime.utcnow().isoformat() + "Z",
                            }
                            error_envelope = make_event_envelope(
                                event_type="orchestration_error",
                                event_data=error_payload,
                                sender="System",
                                topic="session",
                                session_id=session_id,
                            )
                            try:
                                await websocket.app.state.conn_manager.send_to_connection(
                                    conn_id, error_envelope
                                )
                            except Exception as send_exc:
                                logger.debug(
                                    f"[{session_id}] Failed to forward orchestration error: {send_exc}"
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
                f"[{session_id}] Error processing conversation messages: {e}"
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
                    f"[{session_id}][PERF] Cancelling {len(orchestration_tasks)} background orchestration tasks"
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
                    f"[{session_id}][PERF] Background task cleanup complete"
                )

            # Clean up session resources directly through connection manager
            conn_manager = websocket.app.state.conn_manager
            connection = conn_manager._conns.get(conn_id)

            if connection and connection.meta.handler:
                # Clean up TTS client
                tts_pool = getattr(websocket.app.state, "tts_pool", None)
                tts_client = connection.meta.handler.get("tts_client")
                tts_released = False

                if tts_client:
                    try:
                        tts_client.stop_speaking()
                    except Exception as e:
                        logger.debug(f"[{session_id}] TTS stop_speaking error: {e}")

                if tts_pool:
                    try:
                        if session_id or tts_client:
                            tts_released = await tts_pool.release_for_session(
                                session_id, tts_client
                            )
                            if tts_released:
                                if tts_pool.session_awareness_enabled:
                                    logger.info(
                                        f"[{session_id}] Released dedicated TTS client"
                                    )
                                else:
                                    logger.info(
                                        "Released pooled TTS client during cleanup"
                                    )
                    except Exception as e:
                        logger.error(f"[{session_id}] Error releasing TTS client: {e}")

                if connection.meta.handler:
                    connection.meta.handler["tts_client"] = None
                    connection.meta.handler["audio_playing"] = False
                    connection.meta.handler["tts_cancel_event"] = None

                # Clean up STT client
                stt_client = connection.meta.handler.get("stt_client")
                if stt_client and hasattr(websocket.app.state, "stt_pool"):
                    try:
                        stt_client.stop()
                        released = await websocket.app.state.stt_pool.release_for_session(
                            session_id, stt_client
                        )
                        if released:
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

            logger.info(f"[{session_id}] Session cleanup complete")

            # Unregister from connection manager (this also cleans up handler if attached)
            if conn_id:
                await websocket.app.state.conn_manager.unregister(conn_id)
                logger.info(
                    f"[{session_id}] Conversation connection {conn_id} unregistered from manager"
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
                        f"[{session_id}] Conversation removed. Active sessions: {remaining_count}"
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
                    await build_and_flush(
                        memory_manager, websocket.app.state.cosmos
                    )
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
