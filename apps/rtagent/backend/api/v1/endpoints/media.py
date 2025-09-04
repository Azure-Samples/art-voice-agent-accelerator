"""
Media Management Endpoints - V1 Enterprise Architecture
======================================================

REST API endpoints for audio streaming, transcription, and media processing.
Provides enterprise-grade ACS media streaming with pluggable orchestrator support.

V1 Architecture Improvements:
- Clean separation of concerns with focused helper functions
- Consistent error handling and tracing patterns
- Modular dependency management and validation
- Enhanced session management with proper resource cleanup
- Integration with V1 ACS media handler and orchestrator system
- Production-ready WebSocket handling with graceful failure modes

Key V1 Features:
- Pluggable orchestrator support for different conversation engines
- Enhanced observability with OpenTelemetry tracing
- Robust error handling and resource cleanup
- Session-based media streaming with proper state management
- Clean abstractions for testing and maintenance

WebSocket Flow:
1. Accept connection and validate dependencies
2. Authenticate if required
3. Extract and validate call connection ID
4. Create appropriate media handler (Media/Transcription mode)
5. Process streaming messages with error handling
6. Clean up resources on disconnect/error
"""

import os
from typing import Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.websockets import WebSocketState
import asyncio
import json
import uuid

from datetime import datetime

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from apps.rtagent.backend.api.v1.schemas.media import (
    MediaSessionRequest,
    MediaSessionResponse,
    AudioStreamStatus,
)

# Import from config system
from config import ACS_STREAMING_MODE
from config.app_settings import (
    ENABLE_AUTH_VALIDATION,
    AZURE_VOICE_LIVE_ENDPOINT,
    AZURE_VOICE_LIVE_MODEL,
)
from src.speech.speech_recognizer import StreamingSpeechRecognizerFromBytes
from src.enums.stream_modes import StreamMode
from src.stateful.state_managment import MemoManager
from apps.rtagent.backend.src.utils.tracing import log_with_context
from apps.rtagent.backend.src.utils.auth import validate_acs_ws_auth, AuthError
from utils.ml_logging import get_logger
from src.tools.latency_tool import LatencyTool
from azure.communication.callautomation import PhoneNumberIdentifier

# Import V1 components
from ..handlers.acs_media_lifecycle import ACSMediaHandler
from ..handlers.voice_live_handler import VoiceLiveHandler

from ..dependencies.orchestrator import get_orchestrator

logger = get_logger("api.v1.endpoints.media")
tracer = trace.get_tracer(__name__)

router = APIRouter()


@router.get("/status", response_model=dict, summary="Get Media Streaming Status")
async def get_media_status():
    """
    Get the current status of media streaming configuration.

    :return: Current media streaming configuration and status
    :rtype: dict
    """
    return {
        "status": "available",
        "streaming_mode": str(ACS_STREAMING_MODE),
        "websocket_endpoint": "/api/v1/media/stream",
        "protocols_supported": ["WebSocket"],
        "features": {
            "real_time_audio": True,
            "transcription": True,
            "orchestrator_support": True,
            "session_management": True,
        },
        "version": "v1",
    }


@router.post(
    "/sessions", response_model=MediaSessionResponse, summary="Create Media Session"
)
async def create_media_session(request: MediaSessionRequest) -> MediaSessionResponse:
    """
    Create a new media streaming session for Azure Communication Services.

    Initializes a media session with specified audio configuration and returns
    WebSocket connection details for real-time audio streaming. This endpoint
    prepares the infrastructure for bidirectional media communication with
    configurable audio parameters.

    Args:
        request: Media session configuration including call connection ID, 
                audio format, sample rate, and streaming options.

    Returns:
        MediaSessionResponse: Session details containing unique session ID,
        WebSocket URL for streaming, status, and audio configuration.

    Raises:
        HTTPException: When session creation fails due to invalid configuration
                      or system resource constraints.

    Example:
        >>> request = MediaSessionRequest(call_connection_id="call_123")
        >>> response = await create_media_session(request)
        >>> print(response.websocket_url)
    """
    session_id = str(uuid.uuid4())

    return MediaSessionResponse(
        session_id=session_id,
        websocket_url=f"/api/v1/media/stream?call_connection_id={request.call_connection_id}",
        status=AudioStreamStatus.PENDING,
        call_connection_id=request.call_connection_id,
        created_at=datetime.utcnow(),
    )


@router.get(
    "/sessions/{session_id}", response_model=dict, summary="Get Media Session Status"
)
async def get_media_session(session_id: str) -> dict:
    """
    Retrieve status and metadata for a specific media session.

    Queries the current state of an active media session including connection
    status, WebSocket state, and session configuration details. Used for
    monitoring and debugging media streaming sessions.

    Args:
        session_id: Unique identifier for the media session to query.

    Returns:
        dict: Session information including status, connection state, creation
        timestamp, and API version details.

    Example:
        >>> session_info = await get_media_session("media_session_123")
        >>> print(session_info["status"])
    """
    # This is a placeholder - in a real implementation, you'd query session state
    return {
        "session_id": session_id,
        "status": "active",
        "websocket_connected": False,  # Would check actual connection status
        "created_at": datetime.utcnow().isoformat(),
        "version": "v1",
    }


@router.websocket("/stream")
async def acs_media_stream(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for enterprise-grade Azure Communication Services media streaming.

    Handles real-time bidirectional audio streaming with comprehensive session
    management, pluggable orchestrator support, and production-ready error
    handling. Supports multiple streaming modes including media processing,
    transcription, and live voice interaction.

    Args:
        websocket: WebSocket connection from Azure Communication Services for
                  real-time media data exchange.

    Raises:
        WebSocketDisconnect: When client disconnects normally or abnormally.
        HTTPException: When dependencies fail validation or initialization errors occur.

    Note:
        Session ID coordination: Uses browser session ID when available for UI
        dashboard integration, otherwise creates media-specific session for
        direct ACS calls.
    """
    handler = None
    call_connection_id = None
    session_id = None
    conn_id = None
    orchestrator = get_orchestrator()
    try:
        # Extract call_connection_id from WebSocket query parameters or headers
        query_params = dict(websocket.query_params)
        call_connection_id = query_params.get("call_connection_id")
        logger.debug(f"🔍 Query params: {query_params}")

        # If not in query params, check headers
        headers_dict = dict(websocket.headers)
        if not call_connection_id:
            call_connection_id = headers_dict.get("x-ms-call-connection-id")
            logger.debug(f"🔍 Headers: {headers_dict}")

        # 🎯 CRITICAL FIX: Use browser session_id if provided, otherwise create media-specific session
        # This enables UI dashboard to see ACS call progress by sharing the same session ID
        browser_session_id = query_params.get("session_id") or headers_dict.get(
            "x-session-id"
        )

        # If no browser session ID provided via params/headers, check Redis mapping
        if not browser_session_id and call_connection_id:
            try:
                stored_session_id = await websocket.app.state.redis.get_value_async(
                    f"call_session_map:{call_connection_id}"
                )
                if stored_session_id:
                    browser_session_id = stored_session_id
                    logger.info(
                        f"🔍 Retrieved stored browser session ID: {browser_session_id}"
                    )
            except Exception as e:
                logger.warning(f"Failed to retrieve session mapping: {e}")

        if browser_session_id:
            # Use the browser's session ID for UI/ACS coordination
            session_id = browser_session_id
            logger.info(f"🔗 Using browser session ID for ACS call: {session_id}")
        else:
            # Fallback to media-specific session (for direct ACS calls)
            session_id = (
                f"media_{call_connection_id}"
                if call_connection_id
                else f"media_{str(uuid.uuid4())[:8]}"
            )
            logger.info(f"📞 Created ACS-only session ID: {session_id}")
        # Start tracing with valid call connection ID
        with tracer.start_as_current_span(
            "api.v1.media.websocket_accept",
            kind=SpanKind.SERVER,
            attributes={
                "api.version": "v1",
                "media.session_id": session_id,
                "call.connection.id": call_connection_id,
                "network.protocol.name": "websocket",
            },
        ) as accept_span:
            # Clean single-call registration with call validation
            conn_id = await websocket.app.state.conn_manager.register(
                websocket,
                client_type="media",
                call_id=call_connection_id,
                session_id=session_id,
                topics={"media"},
                accept_already_done=False,  # Let manager handle accept cleanly
            )

            # Set up WebSocket state attributes for compatibility with orchestrator
            websocket.state.conn_id = conn_id
            websocket.state.session_id = session_id
            websocket.state.call_connection_id = call_connection_id

            logger.info(
                f"🔍 DEBUG WebSocket state set: session_id='{session_id}', call_connection_id='{call_connection_id}', conn_id='{conn_id}'"
            )

            accept_span.set_attribute("call.connection.id", call_connection_id)
            logger.info(
                f"WebSocket connection established for call: {call_connection_id}"
            )

        # Initialize media handler with V1 patterns
        with tracer.start_as_current_span(
            "api.v1.media.initialize_handler",
            kind=SpanKind.CLIENT,
            attributes={
                "api.version": "v1",
                "call.connection.id": call_connection_id,
                "orchestrator.name": getattr(orchestrator, "name", "unknown"),
                "stream.mode": str(ACS_STREAMING_MODE),
            },
        ) as init_span:
            handler = await _create_media_handler(
                websocket=websocket,
                call_connection_id=call_connection_id,
                session_id=session_id,
                orchestrator=orchestrator,
                conn_id=conn_id,  # Pass the connection ID
            )

            # Store the handler object in connection metadata for lifecycle management
            # Note: We keep our metadata dictionary and store the handler separately
            conn_meta = await websocket.app.state.conn_manager.get_connection_meta(
                conn_id
            )
            if conn_meta:
                if not conn_meta.handler:
                    conn_meta.handler = {}
                conn_meta.handler["media_handler"] = handler

            # Start the handler
            await handler.start()
            init_span.set_attribute("handler.initialized", True)

            # Track WebSocket connection for session metrics
            if hasattr(websocket.app.state, "session_metrics"):
                await websocket.app.state.session_metrics.increment_connected()

        # Process media messages with clean loop
        await _process_media_stream(websocket, handler, call_connection_id)

    except WebSocketDisconnect as e:
        _log_websocket_disconnect(e, session_id, call_connection_id)
        # Don't re-raise WebSocketDisconnect as it's a normal part of the lifecycle
    except Exception as e:
        _log_websocket_error(e, session_id, call_connection_id)
        # Only raise non-disconnect errors
        if not isinstance(e, WebSocketDisconnect):
            raise
    finally:
        await _cleanup_websocket_resources(
            websocket, handler, call_connection_id, session_id
        )


# ============================================================================
# V1 Architecture Helper Functions
# ============================================================================


async def _create_media_handler(
    websocket: WebSocket,
    call_connection_id: str,
    session_id: str,
    orchestrator: callable,
    conn_id: str,
):
    """
    Create appropriate media handler based on configured streaming mode.

    Factory function that initializes the correct media handler type based on
    the ACS_STREAMING_MODE configuration. Handles resource acquisition from
    STT/TTS pools, memory manager initialization, and latency tracking setup.

    Args:
        websocket: WebSocket connection for media streaming operations.
        call_connection_id: Unique call connection identifier from ACS.
        session_id: Session identifier for tracking and coordination.
        orchestrator: Conversation orchestrator function for processing.
        conn_id: Connection manager connection ID for lifecycle management.

    Returns:
        Configured media handler instance based on streaming mode
        (ACSMediaHandler for MEDIA mode or VoiceLiveHandler for VOICE_LIVE mode).

    Raises:
        HTTPException: When streaming mode is invalid or resource acquisition fails.

    Note:
        Memory manager uses call_connection_id for Redis lookup but session_id
        for session isolation to ensure proper state management.
    """

    # Handler lifecycle is now managed by ConnectionManager
    # No need for separate handler tracking - ConnectionManager handles this

    redis_mgr = websocket.app.state.redis

    # Load conversation memory - ensure we always have a valid memory manager
    # IMPORTANT: Use call_connection_id for Redis lookup but session_id for memory session ID
    # This ensures proper session isolation while maintaining call state continuity
    try:
        memory_manager = MemoManager.from_redis(call_connection_id, redis_mgr)
        if memory_manager is None:
            logger.warning(
                f"Memory manager from Redis returned None for {call_connection_id}, creating new one with session_id: {session_id}"
            )
            memory_manager = MemoManager(session_id=session_id)
        else:
            # Update the session_id in case we loaded from a different session mapping
            memory_manager.session_id = session_id
            logger.info(
                f"Updated memory manager session_id to: {session_id} (call_connection_id: {call_connection_id})"
            )
    except Exception as e:
        logger.error(
            f"Failed to load memory manager from Redis for {call_connection_id}: {e}"
        )
        logger.info(
            f"Creating new memory manager for session_id: {session_id} (call_connection_id: {call_connection_id})"
        )
        memory_manager = MemoManager(session_id=session_id)

    # Initialize latency tracking with proper connection manager access
    # Use connection_id stored during registration instead of direct WebSocket state access

    latency_tool = LatencyTool(memory_manager)

    # Set up WebSocket state for orchestrator compatibility
    websocket.state.lt = latency_tool
    websocket.state.cm = memory_manager
    websocket.state.is_synthesizing = False

    # Store latency tool and other handler metadata via connection manager
    conn_meta = await websocket.app.state.conn_manager.get_connection_meta(conn_id)
    if conn_meta:
        if not conn_meta.handler:
            conn_meta.handler = {}
        conn_meta.handler["lt"] = latency_tool
        conn_meta.handler["_greeting_ttfb_stopped"] = False

    latency_tool.start("greeting_ttfb")

    # Set up call context using connection manager metadata
    target_phone_number = memory_manager.get_context("target_number")
    if target_phone_number and conn_meta:
        conn_meta.handler["target_participant"] = PhoneNumberIdentifier(
            target_phone_number
        )

    if conn_meta:
        conn_meta.handler["cm"] = memory_manager
        conn_meta.handler[
            "call_conn"
        ] = websocket.app.state.acs_caller.get_call_connection(call_connection_id)

    if ACS_STREAMING_MODE == StreamMode.MEDIA:
        # Use the V1 ACS media handler - acquire recognizer from pool
        try:
            # Defensive pool monitoring to prevent deadlocks
            stt_queue_size = websocket.app.state.stt_pool._q.qsize()
            tts_queue_size = websocket.app.state.tts_pool._q.qsize()
            logger.info(
                f"Pool status before acquire: STT={stt_queue_size}, TTS={tts_queue_size}"
            )

            per_conn_recognizer = await websocket.app.state.stt_pool.acquire()
            per_conn_synthesizer = await websocket.app.state.tts_pool.acquire()

            # Set up WebSocket state for orchestrator compatibility
            websocket.state.tts_client = per_conn_synthesizer

            # Try to allocate dedicated TTS client for ACS media
            if hasattr(websocket.app.state, "dedicated_tts_manager"):
                try:
                    (
                        dedicated_tts,
                        client_tier,
                    ) = await websocket.app.state.dedicated_tts_manager.get_dedicated_client(
                        call_connection_id
                    )
                    websocket.state.tts_client = (
                        dedicated_tts  # Override with dedicated client
                    )
                    websocket.state.session_id = call_connection_id  # Store for cleanup
                    logger.info(
                        f"Allocated dedicated TTS client for ACS call {call_connection_id} (tier={client_tier.value})"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to allocate dedicated TTS client for ACS call {call_connection_id}: {e}"
                    )

            if conn_meta:
                conn_meta.handler["stt_client"] = per_conn_recognizer
                conn_meta.handler[
                    "tts_client"
                ] = (
                    websocket.state.tts_client
                )  # Use the final client (dedicated or fallback)

            logger.info(
                f"Successfully acquired STT & TTS from pools for ACS call {call_connection_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to acquire pool resources for {call_connection_id}: {e}"
            )
            # Ensure partial cleanup if one acquire succeeded
            stt_client = conn_meta.handler.get("stt_client") if conn_meta else None
            tts_client = conn_meta.handler.get("tts_client") if conn_meta else None
            if stt_client:
                await websocket.app.state.stt_pool.release(stt_client)
            if tts_client:
                await websocket.app.state.tts_pool.release(tts_client)
                # Also clear from WebSocket state
                if hasattr(websocket.state, "tts_client"):
                    websocket.state.tts_client = None
            raise
        handler = ACSMediaHandler(
            websocket=websocket,
            orchestrator_func=orchestrator,
            call_connection_id=call_connection_id,
            recognizer=per_conn_recognizer,
            memory_manager=memory_manager,
            session_id=session_id,
        )
        # Handler lifecycle managed by ConnectionManager - no separate registry needed
        logger.info("Created V1 ACS media handler for MEDIA mode")
        return handler

    elif ACS_STREAMING_MODE == StreamMode.VOICE_LIVE:
        # TODO: Wire up the orchestrator to voice live
        handler = VoiceLiveHandler(
            azure_endpoint=AZURE_VOICE_LIVE_ENDPOINT,
            model_name=AZURE_VOICE_LIVE_MODEL,
            session_id=session_id,
            websocket=websocket,
            orchestrator=orchestrator,
        )

        logger.info("Created V1 ACS voice live handler for VOICE_LIVE mode")
        return handler

    else:
        error_msg = f"Unknown streaming mode: {ACS_STREAMING_MODE}"
        logger.error(error_msg)
        await websocket.close(code=1000, reason="Invalid streaming mode")
        raise HTTPException(400, error_msg)


async def _process_media_stream(
    websocket: WebSocket, handler, call_connection_id: str
) -> None:
    """
    Process incoming WebSocket media messages with comprehensive error handling.

    Main message processing loop that receives WebSocket messages and routes
    them to the appropriate handler based on streaming mode. Implements proper
    disconnect handling with differentiation between normal and abnormal
    disconnections for production monitoring.

    Args:
        websocket: WebSocket connection for message processing.
        handler: Media handler instance (ACSMediaHandler or VoiceLiveHandler).
        call_connection_id: Call connection identifier for logging and tracing.

    Raises:
        WebSocketDisconnect: When client disconnects (normal codes 1000/1001
                           are handled gracefully, abnormal codes are re-raised).
        Exception: When message processing fails due to system errors.

    Note:
        Normal disconnects (codes 1000/1001) are logged but not re-raised to
        prevent unnecessary error traces in monitoring systems.
    """
    with tracer.start_as_current_span(
        "api.v1.media.process_stream",
        kind=SpanKind.SERVER,
        attributes={
            "api.version": "v1",
            "call.connection.id": call_connection_id,
            "stream.mode": str(ACS_STREAMING_MODE),
        },
    ) as span:
        logger.info(
            f"🚀 Starting media stream processing for call: {call_connection_id}"
        )

        try:
            # Main message processing loop
            message_count = 0
            while (
                websocket.client_state == WebSocketState.CONNECTED
                and websocket.application_state == WebSocketState.CONNECTED
            ):
                msg = await websocket.receive_text()
                message_count += 1

                # logger.info(f"📨 Received message #{message_count} ({len(msg)} chars) - {msg[:100]}...")
                # Handle message based on streaming mode
                if ACS_STREAMING_MODE == StreamMode.MEDIA:
                    await handler.handle_media_message(msg)
                elif ACS_STREAMING_MODE == StreamMode.TRANSCRIPTION:
                    await handler.handle_transcription_message(msg)
                elif ACS_STREAMING_MODE == StreamMode.VOICE_LIVE:
                    await handler.handle_audio_data(msg)

        except WebSocketDisconnect as e:
            # Handle WebSocket disconnects gracefully - treat healthy disconnects
            # as normal control flow (do not re-raise) so the outer tracing context
            # does not surface a stacktrace for normal call hangups.
            if e.code == 1000:
                logger.info(
                    f"📞 Call ended normally for {call_connection_id} (WebSocket code 1000)"
                )
                span.set_status(Status(StatusCode.OK))
                # Return cleanly to avoid the exception bubbling up into tracing
                return
            elif e.code == 1001:
                logger.info(
                    f"📞 Call ended - endpoint going away for {call_connection_id} (WebSocket code 1001)"
                )
                span.set_status(Status(StatusCode.OK))
                return
            else:
                logger.warning(
                    f"📞 Call disconnected abnormally for {call_connection_id} (WebSocket code {e.code}): {e.reason}"
                )
                span.set_status(
                    Status(
                        StatusCode.ERROR, f"Abnormal disconnect: {e.code} - {e.reason}"
                    )
                )
                # Re-raise abnormal disconnects so outer layers can handle/log them
                raise
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, f"Stream processing error: {e}"))
            logger.error(f"❌ Error in media stream processing: {e}")
            raise


def _log_websocket_disconnect(
    e: WebSocketDisconnect, session_id: str, call_connection_id: Optional[str]
) -> None:
    """
    Log WebSocket disconnection with appropriate level.

    :param e: WebSocket disconnect exception
    :type e: WebSocketDisconnect
    :param session_id: Session identifier for logging
    :type session_id: str
    :param call_connection_id: Call connection identifier for logging
    :type call_connection_id: Optional[str]
    """
    if e.code == 1000:
        log_with_context(
            logger,
            "info",
            "📞 Call ended normally - healthy WebSocket disconnect",
            operation="websocket_disconnect_normal",
            session_id=session_id,
            call_connection_id=call_connection_id,
            disconnect_code=e.code,
            api_version="v1",
        )
    elif e.code == 1001:
        log_with_context(
            logger,
            "info",
            "📞 Call ended - endpoint going away (normal)",
            operation="websocket_disconnect_normal",
            session_id=session_id,
            call_connection_id=call_connection_id,
            disconnect_code=e.code,
            api_version="v1",
        )
    else:
        log_with_context(
            logger,
            "warning",
            "📞 Call disconnected abnormally",
            operation="websocket_disconnect_abnormal",
            session_id=session_id,
            call_connection_id=call_connection_id,
            disconnect_code=e.code,
            reason=e.reason,
            api_version="v1",
        )


def _log_websocket_error(
    e: Exception, session_id: str, call_connection_id: Optional[str]
) -> None:
    """
    Log WebSocket errors with full context.

    :param e: Exception that occurred
    :type e: Exception
    :param session_id: Session identifier for logging
    :type session_id: str
    :param call_connection_id: Call connection identifier for logging
    :type call_connection_id: Optional[str]
    """
    if isinstance(e, asyncio.CancelledError):
        log_with_context(
            logger,
            "info",
            "WebSocket cancelled",
            operation="websocket_error",
            session_id=session_id,
            call_connection_id=call_connection_id,
            api_version="v1",
        )
    else:
        log_with_context(
            logger,
            "error",
            "WebSocket error",
            operation="websocket_error",
            session_id=session_id,
            call_connection_id=call_connection_id,
            error=str(e),
            error_type=type(e).__name__,
            api_version="v1",
        )


async def _cleanup_websocket_resources(
    websocket: WebSocket, handler, call_connection_id: Optional[str], session_id: str
) -> None:
    """
    Clean up WebSocket resources following V1 patterns.

    :param websocket: WebSocket connection to clean up
    :type websocket: WebSocket
    :param handler: Media handler to stop and clean up
    :param call_connection_id: Call connection identifier for cleanup
    :type call_connection_id: Optional[str]
    :param session_id: Session identifier for logging
    :type session_id: str
    """
    with tracer.start_as_current_span(
        "api.v1.media.cleanup_resources",
        kind=SpanKind.INTERNAL,
        attributes={
            "api.version": "v1",
            "session_id": session_id,
            "call.connection.id": call_connection_id,
        },
    ) as span:
        try:
            # Stop and cleanup handler first
            if handler:
                try:
                    await handler.stop()
                    logger.info("Media handler stopped successfully")
                except Exception as e:
                    logger.error(f"Error stopping media handler: {e}")
                    span.set_status(
                        Status(StatusCode.ERROR, f"Handler cleanup error: {e}")
                    )

            # Clean up media session resources through connection manager metadata
            conn_manager = websocket.app.state.conn_manager
            if hasattr(websocket.state, "conn_id") and websocket.state.conn_id:
                connection = conn_manager._conns.get(websocket.state.conn_id)

                if (
                    connection
                    and connection.meta.handler
                    and isinstance(connection.meta.handler, dict)
                ):
                    # Clean up TTS client
                    tts_client = connection.meta.handler.get("tts_client")
                    if tts_client and hasattr(websocket.app.state, "tts_pool"):
                        try:
                            tts_client.stop_speaking()
                            await websocket.app.state.tts_pool.release(tts_client)
                            logger.info("Released TTS client during media cleanup")
                        except Exception as e:
                            logger.error(f"Error releasing TTS client: {e}")

                    # Clean up STT client
                    stt_client = connection.meta.handler.get("stt_client")
                    if stt_client and hasattr(websocket.app.state, "stt_pool"):
                        try:
                            stt_client.stop()
                            await websocket.app.state.stt_pool.release(stt_client)
                            logger.info("Released STT client during media cleanup")
                        except Exception as e:
                            logger.error(f"Error releasing STT client: {e}")

                    # Clean up any other tracked tasks
                    tts_tasks = connection.meta.handler.get("tts_tasks")
                    if tts_tasks:
                        for task in list(tts_tasks):
                            if not task.done():
                                task.cancel()
                                logger.debug("Cancelled TTS task during media cleanup")

                logger.info(f"Media session cleanup complete for {call_connection_id}")

                # Unregister from connection manager
                try:
                    await websocket.app.state.conn_manager.unregister(
                        websocket.state.conn_id
                    )
                    logger.info(
                        f"Unregistered from connection manager: {websocket.state.conn_id}"
                    )
                except Exception as e:
                    logger.error(f"Error unregistering from connection manager: {e}")

            # Close WebSocket if still connected
            if (
                websocket.client_state == WebSocketState.CONNECTED
                and websocket.application_state == WebSocketState.CONNECTED
            ):
                await websocket.close()
                logger.info("WebSocket connection closed")

            # Clean up latency timers on session disconnect
            if (
                connection
                and hasattr(connection.meta, "handler")
                and connection.meta.handler
            ):
                latency_tool = connection.meta.handler.get("latency_tool")
                if latency_tool and hasattr(latency_tool, "cleanup_timers"):
                    try:
                        latency_tool.cleanup_timers()
                        logger.debug("Cleaned up latency timers during media cleanup")
                    except Exception as e:
                        logger.error(f"Error cleaning up latency timers: {e}")

            # Release dedicated TTS client for ACS media
            if (
                hasattr(websocket.app.state, "dedicated_tts_manager")
                and call_connection_id
            ):
                try:
                    released = await websocket.app.state.dedicated_tts_manager.release_session_client(
                        call_connection_id
                    )
                    if released:
                        logger.info(
                            f"Released dedicated TTS client for ACS call {call_connection_id}"
                        )
                except Exception as e:
                    logger.error(
                        f"Error releasing dedicated TTS client for ACS call {call_connection_id}: {e}"
                    )

            # Track WebSocket disconnection for session metrics
            if hasattr(websocket.app.state, "session_metrics"):
                await websocket.app.state.session_metrics.increment_disconnected()

            span.set_status(Status(StatusCode.OK))
            log_with_context(
                logger,
                "info",
                "WebSocket cleanup complete",
                operation="websocket_cleanup",
                call_connection_id=call_connection_id,
                session_id=session_id,
                api_version="v1",
            )

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, f"Cleanup error: {e}"))
            logger.error(f"Error during cleanup: {e}")
