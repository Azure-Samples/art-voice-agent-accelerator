"""
Media Management Endpoints - V1 Enterprise Architecture
======================================================

WebSocket endpoint for ACS media streaming.

WebSocket Flow:
1. Accept connection and extract call_connection_id
2. Resolve session ID (browser session or ACS-only)
3. Create ACSMediaHandler (handles STT/TTS pool acquisition)
4. Process streaming messages
5. Clean up resources on disconnect (handler releases pools)
"""

import asyncio
import uuid

from apps.artagent.backend.src.ws_helpers.shared_ws import send_agent_inventory
from apps.artagent.backend.voice import VoiceLiveSDKHandler
from config import ACS_STREAMING_MODE
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from src.enums.stream_modes import StreamMode
from src.pools.session_manager import SessionContext
from src.stateful.state_managment import MemoManager
from utils.ml_logging import get_logger
from utils.session_context import session_context

from ..handlers.media_handler import MediaHandler, MediaHandlerConfig, TransportType

logger = get_logger("api.v1.endpoints.media")
tracer = trace.get_tracer(__name__)
router = APIRouter()


# ============================================================================
# Resolution Helpers
# ============================================================================


async def _resolve_stream_mode(redis_mgr, call_connection_id: str | None) -> StreamMode:
    """Resolve the effective streaming mode for a call."""
    if not call_connection_id or redis_mgr is None:
        return ACS_STREAMING_MODE
    try:
        stored = await redis_mgr.get_value_async(f"call_stream_mode:{call_connection_id}")
        if stored:
            return StreamMode.from_string(
                stored.decode() if isinstance(stored, bytes) else str(stored)
            )
    except Exception:
        pass
    return ACS_STREAMING_MODE


async def _resolve_session_id(
    app_state, call_connection_id: str | None, query_params: dict, headers: dict
) -> str:
    """Resolve session ID: query params > headers > Redis > generate new."""
    session_id = query_params.get("session_id") or headers.get("x-session-id")
    if session_id:
        return session_id

    if call_connection_id and app_state:
        redis_mgr = getattr(app_state, "redis", None)
        if redis_mgr:
            for key in [
                f"call_session_map:{call_connection_id}",
                f"call_session_mapping:{call_connection_id}",
            ]:
                try:
                    value = await redis_mgr.get_value_async(key)
                    if value:
                        return value.decode() if isinstance(value, bytes) else str(value)
                except Exception:
                    pass

    return f"media_{call_connection_id}" if call_connection_id else f"media_{uuid.uuid4().hex[:8]}"


# ============================================================================
# REST Endpoints
# ============================================================================


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
    redis_mgr = getattr(websocket.app.state, "redis", None)
    stream_mode = ACS_STREAMING_MODE

    # Extract call_connection_id from query params or headers early
    query_params = dict(websocket.query_params)
    headers_dict = dict(websocket.headers)
    call_connection_id = query_params.get("call_connection_id") or headers_dict.get(
        "x-ms-call-connection-id"
    )

    # Resolve session ID early for context
    session_id = await _resolve_session_id(
        websocket.app.state, call_connection_id, query_params, headers_dict
    )

    # Wrap entire session in session_context for automatic correlation
    # All logs and spans within this block inherit call_connection_id and session_id
    async with session_context(
        call_connection_id=call_connection_id,
        session_id=session_id,
        transport_type="ACS",
        component="media.stream",
    ):
        try:
            logger.info(
                "Session resolved for call",
                extra={"call_connection_id": call_connection_id, "session_id": session_id},
            )

            stream_mode = await _resolve_stream_mode(redis_mgr, call_connection_id)
            websocket.state.stream_mode = stream_mode

            # Accept WebSocket and register connection
            with tracer.start_as_current_span(
                "api.v1.media.websocket_accept",
                kind=SpanKind.SERVER,
                attributes={
                    "media.session_id": session_id,
                    "call.connection.id": call_connection_id,
                    "streaming.mode": str(stream_mode),
                },
            ):
                conn_id = await websocket.app.state.conn_manager.register(
                    websocket,
                    client_type="media",
                    call_id=call_connection_id,
                    session_id=session_id,
                    topics={"media"},
                    accept_already_done=False,
                )
                websocket.state.conn_id = conn_id
                websocket.state.session_id = session_id
                websocket.state.call_connection_id = call_connection_id
                logger.info("WebSocket connected for call %s", call_connection_id)

            # Emit agent inventory to dashboards for this session
            try:
                await send_agent_inventory(
                    websocket.app.state, session_id=session_id, call_id=call_connection_id
                )
            except Exception:
                logger.debug("Failed to emit agent inventory", exc_info=True)

            # Initialize media handler
            with tracer.start_as_current_span(
                "api.v1.media.initialize_handler",
                kind=SpanKind.CLIENT,
                attributes={
                    "call.connection.id": call_connection_id,
                    "stream.mode": str(stream_mode),
                },
            ):
                handler = await _create_media_handler(
                    websocket=websocket,
                    call_connection_id=call_connection_id,
                    session_id=session_id,
                    stream_mode=stream_mode,
                )

                # Store handler in connection metadata
                conn_meta = await websocket.app.state.conn_manager.get_connection_meta(conn_id)
                if conn_meta:
                    conn_meta.handler = conn_meta.handler or {}
                    conn_meta.handler["media_handler"] = handler

                await handler.start()
                await websocket.app.state.session_metrics.increment_connected()

            # Process media messages
            await _process_media_stream(websocket, handler, call_connection_id, stream_mode)

        except WebSocketDisconnect as e:
            _log_websocket_disconnect(e, session_id, call_connection_id)
            # Don't re-raise WebSocketDisconnect as it's a normal part of the lifecycle
        except Exception as e:
            _log_websocket_error(e, session_id, call_connection_id)
            # Only raise non-disconnect errors
            if not isinstance(e, WebSocketDisconnect):
                raise
        finally:
            await _cleanup_websocket_resources(websocket, handler, call_connection_id, session_id)


# ============================================================================
# Handler Factory
# ============================================================================


async def _create_media_handler(
    websocket: WebSocket,
    call_connection_id: str,
    session_id: str,
    stream_mode: StreamMode,
):
    """Create appropriate media handler based on streaming mode."""
    if stream_mode == StreamMode.MEDIA:
        config = MediaHandlerConfig(
            websocket=websocket,
            session_id=session_id,
            transport=TransportType.ACS,
            call_connection_id=call_connection_id,
            stream_mode=stream_mode,
        )
        return await MediaHandler.create(config, websocket.app.state)
    elif stream_mode == StreamMode.VOICE_LIVE:
        # Initialize MemoManager with session context for VoiceLive
        # This ensures greeting can access caller_name, session_profile, etc.
        redis_mgr = getattr(websocket.app.state, "redis", None)
        memory_manager = (
            MemoManager.from_redis(session_id, redis_mgr)
            if redis_mgr
            else MemoManager(session_id=session_id)
        )

        # Set up session context on websocket.state (consistent with browser.py)
        websocket.state.cm = memory_manager
        websocket.state.session_context = SessionContext(
            session_id=session_id,
            memory_manager=memory_manager,
            websocket=websocket,
        )
        websocket.state.session_id = session_id

        logger.debug(
            "[%s] VoiceLive session context initialized | caller_name=%s",
            session_id[:8],
            memory_manager.get_value_from_corememory("caller_name", None),
        )

        return VoiceLiveSDKHandler(
            websocket=websocket,
            session_id=session_id,
            call_connection_id=call_connection_id,
        )
    else:
        await websocket.close(code=1000, reason="Invalid streaming mode")
        raise HTTPException(400, f"Unknown streaming mode: {stream_mode}")


async def _process_media_stream(
    websocket: WebSocket,
    handler,
    call_connection_id: str,
    stream_mode: StreamMode,
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
            "stream.mode": str(stream_mode),
        },
    ) as span:
        logger.info(f"[{call_connection_id}]🚀 Starting media stream processing for call")

        try:
            # Main message processing loop
            message_count = 0
            while (
                websocket.client_state == WebSocketState.CONNECTED
                and websocket.application_state == WebSocketState.CONNECTED
            ):
                raw_message = await websocket.receive()
                message_count += 1

                if raw_message.get("type") == "websocket.close":
                    logger.info(
                        f"[{call_connection_id}] WebSocket requested close (code={raw_message.get('code')})"
                    )
                    raise WebSocketDisconnect(code=raw_message.get("code", 1000))

                if raw_message.get("type") not in {"websocket.receive", "websocket.disconnect"}:
                    logger.debug(
                        f"[{call_connection_id}] Ignoring unexpected message type={raw_message.get('type')}"
                    )
                    continue

                msg_text = raw_message.get("text")
                if msg_text is None:
                    if raw_message.get("bytes"):
                        logger.debug(
                            f"[{call_connection_id}] Received binary frame ({len(raw_message['bytes'])} bytes)"
                        )
                        continue
                    logger.warning(
                        f"[{call_connection_id}] Received message without text payload: keys={list(raw_message.keys())}"
                    )
                    continue

                # Handle message based on streaming mode
                if stream_mode == StreamMode.MEDIA:
                    await handler.handle_media_message(msg_text)
                elif stream_mode == StreamMode.TRANSCRIPTION:
                    await handler.handle_transcription_message(msg_text)
                elif stream_mode == StreamMode.VOICE_LIVE:
                    await handler.handle_audio_data(msg_text)

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
                    Status(StatusCode.ERROR, f"Abnormal disconnect: {e.code} - {e.reason}")
                )
                # Re-raise abnormal disconnects so outer layers can handle/log them
                raise
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, f"Stream processing error: {e}"))
            logger.exception(f"[{call_connection_id}]❌ Error in media stream processing")
            raise


# ============================================================================
# Logging Helpers
# ============================================================================


def _log_websocket_disconnect(
    e: WebSocketDisconnect, session_id: str, call_connection_id: str | None
) -> None:
    """Log WebSocket disconnection with appropriate level."""
    if e.code in (1000, 1001):
        logger.info("Call ended normally (code=%s) for %s", e.code, call_connection_id)
    else:
        logger.warning(
            "Call disconnected abnormally (code=%s, reason=%s) for %s",
            e.code,
            e.reason,
            call_connection_id,
        )


def _log_websocket_error(e: Exception, session_id: str, call_connection_id: str | None) -> None:
    """Log WebSocket errors."""
    if isinstance(e, asyncio.CancelledError):
        logger.info("WebSocket cancelled for %s", call_connection_id)
    else:
        logger.error("WebSocket error for %s: %s (%s)", call_connection_id, e, type(e).__name__)


# ============================================================================
# Cleanup
# ============================================================================


async def _cleanup_websocket_resources(
    websocket: WebSocket, handler, call_connection_id: str | None, session_id: str
) -> None:
    """Clean up WebSocket resources: handler and connection manager."""
    with tracer.start_as_current_span(
        "api.v1.media.cleanup_resources",
        kind=SpanKind.INTERNAL,
        attributes={"session_id": session_id, "call.connection.id": call_connection_id},
    ) as span:
        try:
            # Stop handler (releases pool resources internally)
            if handler:
                try:
                    await handler.stop()
                except Exception as e:
                    logger.error("Error stopping media handler: %s", e)

            # Unregister connection
            conn_id = getattr(websocket.state, "conn_id", None)
            if conn_id:
                try:
                    await websocket.app.state.conn_manager.unregister(conn_id)
                except Exception as e:
                    logger.error("Error unregistering connection: %s", e)

            # Close WebSocket if still connected
            if (
                websocket.client_state == WebSocketState.CONNECTED
                and websocket.application_state == WebSocketState.CONNECTED
            ):
                await websocket.close()

            # Track metrics
            if hasattr(websocket.app.state, "session_metrics"):
                await websocket.app.state.session_metrics.increment_disconnected()

            span.set_status(Status(StatusCode.OK))

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, f"Cleanup error: {e}"))
            logger.error("Error during cleanup: %s", e)
