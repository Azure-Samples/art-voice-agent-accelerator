"""
Genesys AudioConnector WebSocket Endpoint
==========================================

Provides the WebSocket endpoint for Genesys Cloud AudioConnector integration.
Implements the AudioHook v2 server-side protocol, bridging Genesys telephony
to the ART VoiceLive multi-agent orchestrator.

WebSocket Flow:
    1. Genesys connects with ``audiohook-session-id`` header
    2. Handler accepts and starts outbound writer
    3. Client sends ``open`` → handler connects to VoiceLive + starts orchestrator
    4. Binary audio frames stream bidirectionally with codec conversion
    5. On ``close`` or disconnect → graceful shutdown

Endpoint:
    GET /api/v1/genesys/health  → Health check
    WS  /api/v1/genesys/stream  → AudioHook v2 WebSocket
"""

import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from opentelemetry import trace
from utils.ml_logging import get_logger

from apps.artagent.backend.voice.genesys.handler import GenesysVoiceLiveHandler

logger = get_logger("api.v1.endpoints.genesys")
tracer = trace.get_tracer(__name__)

router = APIRouter(tags=["Genesys AudioConnector"])


@router.get("/health")
async def genesys_health():
    """Health check for Genesys AudioConnector endpoint."""
    return {"status": "ok", "service": "genesys-audiohook"}


@router.websocket("/stream")
async def genesys_audiohook_stream(websocket: WebSocket):
    """AudioHook v2 WebSocket endpoint for Genesys Cloud AudioConnector.

    Genesys sends ``audiohook-session-id`` as a header or query parameter.
    The handler bridges the AudioHook v2 protocol to VoiceLive SDK for
    real-time AI-powered voice interactions.
    """
    # Extract session ID from Genesys headers
    session_id = websocket.headers.get("audiohook-session-id")
    if not session_id:
        # Fall back to query parameter or generate one
        session_id = websocket.query_params.get("session_id", str(uuid.uuid4()))

    logger.info("[Genesys] WebSocket connect | session=%s", session_id)

    handler = GenesysVoiceLiveHandler(websocket=websocket, session_id=session_id)

    # Genesys AudioHook does NOT negotiate a WebSocket subprotocol — its handshake
    # offers no ``Sec-WebSocket-Protocol`` header. Per RFC 6455 a server must only
    # select a subprotocol the client offered; forcing one (the original
    # ``"audiohook-v2"``) makes strict clients like Genesys abort the handshake with
    # a generic error and empty server logs. Mirror only a subprotocol the client
    # actually offered, otherwise select none.
    offered = websocket.headers.get("sec-websocket-protocol", "")
    offered_protocols = [p.strip() for p in offered.split(",") if p.strip()]
    selected_subprotocol = "audiohook" if "audiohook" in offered_protocols else None
    await websocket.accept(subprotocol=selected_subprotocol)

    try:
        await handler.start()

        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if "text" in message:
                await handler.handle_text_message(message["text"])
            elif "bytes" in message:
                await handler.handle_binary_message(message["bytes"])

    except WebSocketDisconnect:
        logger.info("[Genesys] Client disconnected | session=%s", session_id)
    except Exception:
        logger.exception("[Genesys] WebSocket error | session=%s", session_id)
    finally:
        await handler.stop()
        logger.info("[Genesys] WebSocket closed | session=%s", session_id)
