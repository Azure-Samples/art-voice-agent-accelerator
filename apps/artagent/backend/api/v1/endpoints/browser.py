"""
V1 Browser API Endpoints - Enterprise Architecture
==================================================

WebSocket endpoints for browser-based voice conversations.

Endpoint Architecture:
- /status: Service health and connection statistics
- /dashboard/relay: Dashboard client connections for monitoring
- /conversation: Browser-based voice conversations (Voice Live or Speech Cascade)

Handler Pattern (matches media.py):
- Voice Live: VoiceLiveSDKHandler created directly in endpoint
- Speech Cascade: MediaHandler.create() factory (handles all setup)

The endpoint handles:
1. WebSocket accept/close lifecycle
2. Session ID resolution
3. Connection registration
4. Handler creation and message processing
5. Cleanup orchestration
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from apps.artagent.backend.src.services.acs.session_terminator import (
    TerminationReason,
    terminate_session,
)
from apps.artagent.backend.src.utils.tracing import log_with_context
from apps.artagent.backend.src.ws_helpers.barge_in import BargeInController
from apps.artagent.backend.src.ws_helpers.envelopes import make_status_envelope
from apps.artagent.backend.src.ws_helpers.shared_ws import (
    _get_connection_metadata,
    _set_connection_metadata,
    send_agent_inventory,
)
from apps.artagent.backend.voice import VoiceLiveSDKHandler
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.websockets import WebSocketState
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from src.enums.stream_modes import StreamMode
from src.pools.session_manager import SessionContext
from src.postcall.push import build_and_flush
from src.stateful.state_managment import MemoManager
from utils.ml_logging import get_logger
from utils.session_context import session_context

from apps.artagent.backend.src.orchestration.unified import cleanup_adapter

from ..handlers.media_handler import (
    VOICE_LIVE_PCM_SAMPLE_RATE,
    VOICE_LIVE_SILENCE_GAP_SECONDS,
    VOICE_LIVE_SPEECH_RMS_THRESHOLD,
    MediaHandler,
    MediaHandlerConfig,
    TransportType,
    pcm16le_rms,
)
from ..schemas.realtime import RealtimeStatusResponse

logger = get_logger("api.v1.endpoints.browser")
tracer = trace.get_tracer(__name__)

router = APIRouter()


# =============================================================================
# Status Endpoint
# =============================================================================


@router.get(
    "/status",
    response_model=RealtimeStatusResponse,
    summary="Get Browser Service Status",
    tags=["Browser Status"],
)
async def get_browser_status(request: Request) -> RealtimeStatusResponse:
    """Retrieve browser service status and active connection counts."""
    session_count = await request.app.state.session_manager.get_session_count()
    conn_stats = await request.app.state.conn_manager.stats()
    dashboard_clients = conn_stats.get("by_topic", {}).get("dashboard", 0)

    return RealtimeStatusResponse(
        status="available",
        websocket_endpoints={
            "dashboard_relay": "/api/v1/browser/dashboard/relay",
            "conversation": "/api/v1/browser/conversation",
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


# =============================================================================
# Dashboard Relay Endpoint
# =============================================================================


@router.websocket("/dashboard/relay")
async def dashboard_relay_endpoint(
    websocket: WebSocket,
    session_id: str | None = Query(None),
) -> None:
    """WebSocket endpoint for dashboard clients to receive real-time updates."""
    client_id = str(uuid.uuid4())[:8]
    conn_id = None

    try:
        with tracer.start_as_current_span(
            "api.v1.browser.dashboard_relay_connect",
            kind=SpanKind.SERVER,
            attributes={
                "api.version": "v1",
                "browser.client_id": client_id,
                "network.protocol.name": "websocket",
            },
        ) as span:
            conn_id = await websocket.app.state.conn_manager.register(
                websocket,
                client_type="dashboard",
                topics={"dashboard"},
                session_id=session_id,
                accept_already_done=False,
            )

            if hasattr(websocket.app.state, "session_metrics"):
                await websocket.app.state.session_metrics.increment_connected()

            span.set_status(Status(StatusCode.OK))
            log_with_context(
                logger,
                "info",
                "Dashboard client connected",
                operation="dashboard_connect",
                client_id=client_id,
                conn_id=conn_id,
            )

        # Keep-alive loop
        while _is_connected(websocket):
            await websocket.receive_text()

    except WebSocketDisconnect as e:
        _log_disconnect("dashboard", client_id, e)
    except Exception as e:
        _log_error("dashboard", client_id, e)
        raise
    finally:
        await _cleanup_dashboard(websocket, client_id, conn_id)


# =============================================================================
# Conversation Endpoint
# =============================================================================


@router.websocket("/conversation")
async def browser_conversation_endpoint(
    websocket: WebSocket,
    session_id: str | None = Query(None),
    streaming_mode: str | None = Query(None),
    user_email: str | None = Query(None),
    scenario: str | None = Query(None, description="Scenario name (e.g., 'banking', 'default')"),
) -> None:
    """
    WebSocket endpoint for browser-based voice conversations.

    Supports two modes:
    - Voice Live: VoiceLiveSDKHandler (direct, like media.py)
    - Speech Cascade: MediaHandler.create() factory
    
    Query Parameters:
    - scenario: Industry scenario (banking, default, etc.)
    """
    handler: Any = None  # MediaHandler or VoiceLiveSDKHandler
    memory_manager: MemoManager | None = None
    conn_id: str | None = None

    # Parse streaming mode
    stream_mode = _parse_stream_mode(streaming_mode)
    websocket.state.stream_mode = str(stream_mode)

    # Resolve session ID early for context
    session_id = _resolve_session_id(websocket, session_id)

    # Wrap entire session in session_context for automatic correlation
    # All logs and spans within this block inherit session_id and call_connection_id
    async with session_context(
        call_connection_id=session_id,  # For browser, session_id is the correlation key
        session_id=session_id,
        transport_type="BROWSER",
        component="browser.conversation",
    ):
        try:
            with tracer.start_as_current_span(
                "api.v1.browser.conversation_connect",
                kind=SpanKind.SERVER,
                attributes={
                    "api.version": "v1",
                    "browser.session_id": session_id,
                    "stream.mode": str(stream_mode),
                    "scenario.name": scenario or "default",
                    "network.protocol.name": "websocket",
                },
            ) as span:
                # Register connection
                conn_id = await _register_connection(websocket, session_id)
                websocket.state.conn_id = conn_id

                # Create handler based on mode
                if stream_mode == StreamMode.VOICE_LIVE:
                    handler, memory_manager = await _create_voice_live_handler(
                        websocket, session_id, conn_id, user_email, scenario
                    )
                    metadata = {
                        "cm": memory_manager,
                        "session_id": session_id,
                        "stream_mode": str(stream_mode),
                    }
                else:
                    # Speech Cascade - use MediaHandler factory
                    config = MediaHandlerConfig(
                        session_id=session_id,
                        websocket=websocket,
                        transport=TransportType.BROWSER,
                        conn_id=conn_id,
                        user_email=user_email,
                        scenario=scenario,
                    )
                    handler = await MediaHandler.create(config, websocket.app.state)
                    memory_manager = handler.memory_manager
                    metadata = handler.metadata

                # Register with session manager
                await websocket.app.state.session_manager.add_session(
                    session_id,
                    memory_manager,
                    websocket,
                    metadata=metadata,
                )
                # Emit agent inventory to dashboards for this session
                try:
                    await send_agent_inventory(websocket.app.state, session_id=session_id)
                except Exception:
                    logger.debug("Failed to emit agent inventory", exc_info=True)

                if hasattr(websocket.app.state, "session_metrics"):
                    await websocket.app.state.session_metrics.increment_connected()

                span.set_status(Status(StatusCode.OK))
                log_with_context(
                    logger,
                    "info",
                    "Conversation session initialized",
                    operation="conversation_connect",
                    session_id=session_id,
                    stream_mode=str(stream_mode),
                )

            # Process messages based on mode
            if stream_mode == StreamMode.VOICE_LIVE:
                await _process_voice_live_messages(websocket, handler, session_id, conn_id)
            else:
                # Start speech cascade and run message loop
                await handler.start()
                await handler.run()

        except WebSocketDisconnect as e:
            _log_disconnect("conversation", session_id, e)
        except Exception as e:
            _log_error("conversation", session_id, e)
            raise
        finally:
            await _cleanup_conversation(
                websocket, session_id, handler, memory_manager, conn_id, stream_mode
            )


# =============================================================================
# Voice Live Handler Creation & Processing (matches media.py pattern)
# =============================================================================


async def _create_voice_live_handler(
    websocket: WebSocket,
    session_id: str,
    conn_id: str,
    user_email: str | None,
    scenario: str | None,
) -> tuple[VoiceLiveSDKHandler, MemoManager]:
    """
    Create VoiceLiveSDKHandler with barge-in infrastructure.

    Sets up:
    - Session context and memory manager
    - Barge-in controller with cancellation signals
    - TTS state tracking metadata
    - VoiceLiveSDKHandler instance

    Returns:
        Tuple of (handler, memory_manager).
    """
    redis_mgr = websocket.app.state.redis
    memory_manager = MemoManager.from_redis(session_id, redis_mgr)
    if scenario:
        memory_manager.set_corememory("scenario_name", scenario)

    # Set up session context
    session_context = SessionContext(
        session_id=session_id,
        memory_manager=memory_manager,
        websocket=websocket,
    )
    websocket.state.session_context = session_context
    websocket.state.cm = memory_manager
    websocket.state.session_id = session_id
    websocket.state.scenario = scenario

    # Initialize barge-in state on websocket.state
    cancel_event = asyncio.Event()
    websocket.state.tts_cancel_event = cancel_event
    websocket.state.tts_client = None
    websocket.state.lt = None
    websocket.state.is_synthesizing = False
    websocket.state.audio_playing = False
    websocket.state.tts_cancel_requested = False
    websocket.state.orchestration_tasks = set()

    # Capture event loop for thread-safe scheduling
    try:
        websocket.state._loop = asyncio.get_running_loop()
    except RuntimeError:
        websocket.state._loop = None

    # Metadata accessors for BargeInController
    def get_metadata(key: str, default=None):
        return _get_connection_metadata(websocket, key, default)

    def set_metadata(key: str, value):
        if not _set_connection_metadata(websocket, key, value):
            setattr(websocket.state, key, value)

    def signal_tts_cancel() -> None:
        """Signal cancellation to Voice Live - triggers audio stop on client."""
        evt = get_metadata("tts_cancel_event")
        if not evt:
            return
        loop = getattr(websocket.state, "_loop", None)
        if loop and loop.is_running():
            loop.call_soon_threadsafe(evt.set)
        else:
            try:
                evt.set()
            except Exception as exc:
                logger.debug("[%s] Unable to signal cancel event: %s", session_id, exc)

    # Create barge-in controller
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

    # CRITICAL: Set request_barge_in so VoiceLiveSDKHandler._trigger_barge_in can find it
    websocket.state.request_barge_in = barge_in_controller.request

    # Initialize barge-in tracking metadata
    set_metadata("request_barge_in", barge_in_controller.request)
    set_metadata("last_barge_in_ts", 0.0)
    set_metadata("barge_in_inflight", False)
    set_metadata("last_barge_in_trigger", None)
    set_metadata("tts_cancel_event", cancel_event)
    set_metadata("is_synthesizing", False)
    set_metadata("audio_playing", False)
    set_metadata("tts_cancel_requested", False)

    # Create Voice Live handler
    handler = VoiceLiveSDKHandler(
        websocket=websocket,
        session_id=session_id,
        call_connection_id=session_id,
        transport="realtime",
        user_email=user_email,
    )

    return handler, memory_manager


async def _process_voice_live_messages(
    websocket: WebSocket,
    handler: VoiceLiveSDKHandler,
    session_id: str,
    conn_id: str,
) -> None:
    """
    Process Voice Live PCM frames with RMS-based VAD.

    Matches media.py processing pattern.
    """
    speech_active = False
    silence_started_at: float | None = None

    with tracer.start_as_current_span(
        "api.v1.browser.process_voice_live",
        attributes={"session_id": session_id},
    ) as span:
        try:
            await handler.start()
            websocket.state.voice_live_handler = handler

            # Register handler in connection metadata
            conn_meta = await websocket.app.state.conn_manager.get_connection_meta(conn_id)
            if conn_meta:
                if not conn_meta.handler:
                    conn_meta.handler = {}
                conn_meta.handler["voice_live_handler"] = handler

            # Send readiness status
            try:
                ready_envelope = make_status_envelope(
                    "Voice Live orchestration connected",
                    sender="System",
                    topic="session",
                    session_id=session_id,
                )
                await websocket.app.state.conn_manager.send_to_connection(conn_id, ready_envelope)
            except Exception:
                logger.debug("[%s] Unable to send Voice Live readiness status", session_id)

            # Message processing loop
            while _is_connected(websocket):
                raw_message = await websocket.receive()
                msg_type = raw_message.get("type")

                if msg_type in {"websocket.close", "websocket.disconnect"}:
                    raise WebSocketDisconnect(code=raw_message.get("code", 1000))

                if msg_type != "websocket.receive":
                    continue

                # Handle audio bytes
                audio_bytes = raw_message.get("bytes")
                if audio_bytes:
                    await handler.handle_pcm_chunk(
                        audio_bytes, sample_rate=VOICE_LIVE_PCM_SAMPLE_RATE
                    )

                    # RMS-based speech detection
                    rms_value = pcm16le_rms(audio_bytes)
                    now = time.perf_counter()

                    if rms_value >= VOICE_LIVE_SPEECH_RMS_THRESHOLD:
                        speech_active = True
                        silence_started_at = None
                    elif speech_active:
                        if silence_started_at is None:
                            silence_started_at = now
                        elif now - silence_started_at >= VOICE_LIVE_SILENCE_GAP_SECONDS:
                            await handler.commit_audio_buffer()
                            speech_active = False
                            silence_started_at = None
                    continue

                # Handle text messages
                text_payload = raw_message.get("text")
                if text_payload and text_payload.strip():
                    try:
                        payload = json.loads(text_payload)
                        if not isinstance(payload, dict):
                            payload = {"type": "text", "message": str(payload)}
                        kind = payload.get("kind") or payload.get("type")
                        if kind == "StopAudio":
                            await handler.commit_audio_buffer()
                    except json.JSONDecodeError:
                        await handler.send_text_message(text_payload)

            span.set_status(Status(StatusCode.OK))

        except WebSocketDisconnect:
            raise
        except Exception as exc:
            logger.error("[%s] Voice Live error: %s", session_id, exc, exc_info=True)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            if speech_active:
                try:
                    await handler.commit_audio_buffer()
                except Exception:
                    pass
            await handler.stop()
            if getattr(websocket.state, "voice_live_handler", None) is handler:
                websocket.state.voice_live_handler = None


# =============================================================================
# Helper Functions
# =============================================================================


def _parse_stream_mode(streaming_mode: str | None) -> StreamMode:
    """Parse streaming mode from query parameter."""
    if not streaming_mode:
        return StreamMode.REALTIME
    try:
        return StreamMode.from_string(streaming_mode.strip().lower())
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _resolve_session_id(websocket: WebSocket, session_id: str | None) -> str:
    """Resolve session ID from query param, headers, or generate new UUID."""
    header_call_id = websocket.headers.get("x-ms-call-connection-id")

    if session_id:
        return session_id
    if header_call_id:
        websocket.state.call_connection_id = header_call_id
        websocket.state.acs_bridged_call = True
        return header_call_id

    websocket.state.acs_bridged_call = False
    return str(uuid.uuid4())


async def _register_connection(websocket: WebSocket, session_id: str) -> str:
    """Register WebSocket with connection manager."""
    header_call_id = websocket.headers.get("x-ms-call-connection-id")
    conn_id = await websocket.app.state.conn_manager.register(
        websocket,
        client_type="conversation",
        session_id=session_id,
        call_id=header_call_id,
        topics={"conversation"},
        accept_already_done=False,
    )

    if header_call_id:
        await _bind_call_session(websocket.app.state, header_call_id, session_id, conn_id)

    return conn_id


async def _bind_call_session(
    app_state: Any,
    call_connection_id: str,
    session_id: str,
    conn_id: str,
) -> None:
    """Persist association between ACS call and browser session."""
    ttl_seconds = 60 * 60 * 24  # 24 hours
    redis_mgr = getattr(app_state, "redis", None)

    if redis_mgr and hasattr(redis_mgr, "set_value_async"):
        for redis_key in (
            f"call_session_map:{call_connection_id}",
            f"call_session_mapping:{call_connection_id}",
        ):
            try:
                await redis_mgr.set_value_async(redis_key, session_id, ttl_seconds=ttl_seconds)
            except Exception:
                pass

    conn_manager = getattr(app_state, "conn_manager", None)
    if conn_manager:
        try:
            context = await conn_manager.get_call_context(call_connection_id) or {}
            context.update(
                {
                    "session_id": session_id,
                    "browser_session_id": session_id,
                    "connection_id": conn_id,
                }
            )
            await conn_manager.set_call_context(call_connection_id, context)
        except Exception:
            pass


def _is_connected(websocket: WebSocket) -> bool:
    """Check if WebSocket is still connected."""
    return (
        websocket.client_state == WebSocketState.CONNECTED
        and websocket.application_state == WebSocketState.CONNECTED
    )


# =============================================================================
# Logging Helpers
# =============================================================================


def _log_disconnect(endpoint: str, identifier: str | None, e: WebSocketDisconnect) -> None:
    """Log WebSocket disconnect."""
    level = "info" if e.code == 1000 else "warning"
    log_with_context(
        logger,
        level,
        f"{endpoint.capitalize()} disconnected",
        operation=f"{endpoint}_disconnect",
        identifier=identifier,
        disconnect_code=e.code,
    )


def _log_error(endpoint: str, identifier: str | None, e: Exception) -> None:
    """Log WebSocket error."""
    log_with_context(
        logger,
        "error",
        f"{endpoint.capitalize()} error",
        operation=f"{endpoint}_error",
        identifier=identifier,
        error=str(e),
        error_type=type(e).__name__,
    )


# =============================================================================
# Cleanup Functions
# =============================================================================


async def _cleanup_dashboard(
    websocket: WebSocket,
    client_id: str | None,
    conn_id: str | None,
) -> None:
    """Clean up dashboard connection resources."""
    with tracer.start_as_current_span(
        "api.v1.browser.cleanup_dashboard",
        attributes={"client_id": client_id},
    ) as span:
        try:
            if conn_id:
                await websocket.app.state.conn_manager.unregister(conn_id)

            if hasattr(websocket.app.state, "session_metrics"):
                await websocket.app.state.session_metrics.increment_disconnected()

            if _is_connected(websocket):
                await websocket.close()

            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error("Dashboard cleanup error: %s", e)


async def _cleanup_conversation(
    websocket: WebSocket,
    session_id: str | None,
    handler: Any,  # MediaHandler or VoiceLiveSDKHandler
    memory_manager: MemoManager | None,
    conn_id: str | None,
    stream_mode: StreamMode,
) -> None:
    """Clean up conversation session resources."""
    with tracer.start_as_current_span(
        "api.v1.browser.cleanup_conversation",
        attributes={"session_id": session_id},
    ) as span:
        try:
            # Terminate Voice Live ACS session if needed
            await _terminate_voice_live_if_needed(websocket, session_id)

            # Handler cleanup based on type
            if handler:
                if isinstance(handler, MediaHandler):
                    await handler.stop()
                # VoiceLiveSDKHandler cleanup already done in processing finally block

            # Clear orchestrator adapter cache for this session
            if session_id:
                cleanup_adapter(session_id)

            # Unregister connection
            if conn_id:
                await websocket.app.state.conn_manager.unregister(conn_id)

            # Remove from session manager
            if session_id:
                await websocket.app.state.session_manager.remove_session(session_id)

            # Track disconnect metrics
            if hasattr(websocket.app.state, "session_metrics"):
                await websocket.app.state.session_metrics.increment_disconnected()

            # Close WebSocket
            if _is_connected(websocket):
                await websocket.close()

            # Persist analytics
            if memory_manager and hasattr(websocket.app.state, "cosmos"):
                try:
                    await build_and_flush(memory_manager, websocket.app.state.cosmos)
                except Exception as e:
                    logger.error("[%s] Analytics persist error: %s", session_id, e)

            span.set_status(Status(StatusCode.OK))
            logger.info("[%s] Conversation cleanup complete", session_id)

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error("[%s] Conversation cleanup error: %s", session_id, e)


async def _terminate_voice_live_if_needed(
    websocket: WebSocket,
    session_id: str | None,
) -> None:
    """Terminate ACS Voice Live call if browser disconnects."""
    try:
        stream_mode = str(getattr(websocket.state, "stream_mode", "")).lower()
        is_voice_live = stream_mode == str(StreamMode.VOICE_LIVE).lower()

        if not is_voice_live:
            return
        if not getattr(websocket.state, "acs_bridged_call", False):
            return
        if getattr(websocket.state, "acs_session_terminated", False):
            return

        call_connection_id = getattr(websocket.state, "call_connection_id", None)
        if not call_connection_id:
            return

        await terminate_session(
            websocket,
            is_acs=True,
            call_connection_id=call_connection_id,
            reason=TerminationReason.NORMAL,
        )
        logger.info("[%s] ACS session terminated on frontend disconnect", session_id)
    except Exception as e:
        logger.warning("[%s] ACS termination failed: %s", session_id, e)
