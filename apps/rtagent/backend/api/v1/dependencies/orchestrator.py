"""
Orchestrator Dependency Injection
=================================

Simple orchestrator injection for the V1 API with clean tracing.
Provides a clean interface to the conversation orchestration logic.
"""

from typing import Optional
from fastapi import WebSocket
from websockets.exceptions import ConnectionClosedError
from opentelemetry import trace

from src.stateful.state_managment import MemoManager
from apps.rtagent.backend.src.orchestration.artagent.orchestrator import route_turn
from apps.rtagent.backend.src.utils.tracing import trace_acs_operation
from utils.ml_logging import get_logger

logger = get_logger("api.v1.dependencies.orchestrator")
tracer = trace.get_tracer(__name__)

# Orchestration Dependency Injection Point
# ----------------------------------------
# This module enables a single integration point for orchestration logic,
# allowing external systems (not just API endpoints) to invoke conversation routing
# via route_turn or other orchestrator functions. This pattern supports modular
# expansion (e.g., plugging in different routing strategies or intent handlers)
# without tightly coupling orchestration to API layer specifics.
# E.g:
#   General orchestration -> route_turn
#   Intent mapped orchestration -> route_turn_for_fnol


async def route_conversation_turn(
    cm: MemoManager, transcript: str, ws: WebSocket, **kwargs
) -> None:
    """
    Route a conversation turn through the orchestration system with error handling.

    Processes user input through the conversation orchestrator with comprehensive
    error handling for WebSocket disconnections and system failures. Provides
    tracing and logging for debugging conversation flow issues.

    Args:
        cm: Memory manager instance for conversation state persistence and retrieval.
        transcript: User's transcribed speech text to process through orchestration.
        ws: WebSocket connection for real-time communication and response streaming.
        **kwargs: Additional context including call_id, session_id, and ACS flags.

    Raises:
        Exception: For non-WebSocket related orchestration failures that require
                  upstream handling and recovery.

    Note:
        WebSocket connection errors are handled gracefully and logged without
        re-raising to prevent unnecessary error propagation during normal disconnects.
    """
    call_id = kwargs.get("call_id")
    session_id = getattr(cm, "session_id", None) if cm else None

    with trace_acs_operation(
        tracer,
        logger,
        "route_conversation_turn",
        call_connection_id=call_id,
        session_id=session_id,
        transcript_length=len(transcript) if transcript else 0,
    ) as op:
        try:
            op.log_info(f"Routing conversation turn - transcript: {transcript[:50]}...")

            # Handle potential WebSocket disconnects
            try:
                await route_turn(
                    cm=cm,
                    transcript=transcript,
                    ws=ws,
                    is_acs=kwargs.get("is_acs", True),
                )
                op.log_info("Conversation turn completed successfully")

            except ConnectionClosedError:
                op.log_info("WebSocket connection closed during orchestration")
                return
            except Exception as ws_error:
                # Check if it's a WebSocket-related error
                if (
                    "websocket" in str(ws_error).lower()
                    or "connection" in str(ws_error).lower()
                ):
                    op.log_info(f"WebSocket error during orchestration: {ws_error}")
                    return
                else:
                    # Re-raise non-WebSocket errors
                    raise

        except Exception as e:
            op.set_error(f"Failed to route conversation turn: {e}")
            raise


def get_orchestrator() -> callable:
    """
    FastAPI dependency provider for conversation orchestrator function.

    Returns the route_conversation_turn function for dependency injection into
    WebSocket endpoints and API handlers. Enables clean separation of concerns
    between API layer and conversation orchestration logic.

    Returns:
        callable: The route_conversation_turn function configured for use
        as a FastAPI dependency in endpoint handlers.

    Example:
        >>> @router.websocket("/conversation")
        >>> async def endpoint(ws: WebSocket, orchestrator=Depends(get_orchestrator)):
        ...     await orchestrator(cm, transcript, ws)
    """
    return route_conversation_turn
