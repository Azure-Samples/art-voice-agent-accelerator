"""
Tool Helpers for VoiceLive
==========================

Utilities for emitting tool execution status to the frontend.
These helpers format and broadcast tool_start/tool_end events
for UI display during agent tool calls.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import WebSocket
from utils.ml_logging import get_logger

logger = get_logger("voicelive.tool_helpers")


async def _emit(
    ws: WebSocket, payload: dict, *, is_acs: bool, session_id: str | None = None
) -> None:
    """
    Emit tool status to connected clients.

    - browser `/realtime` → send JSON directly to specific session
    - phone `/call/*` → broadcast to dashboards only for that session

    IMPORTANT: Tool frames are now session-aware to prevent cross-session leakage.
    """
    if is_acs:
        # Use session-aware broadcasting for ACS calls
        if hasattr(ws.app.state, "conn_manager"):
            if session_id:
                # Session-safe: Only broadcast to connections in the same session
                asyncio.create_task(
                    ws.app.state.conn_manager.broadcast_session(session_id, payload)
                )
                logger.debug(
                    "Tool frame broadcasted to session %s: %s",
                    session_id,
                    payload.get("tool", "unknown"),
                )
            else:
                # Fallback to legacy broadcast
                asyncio.create_task(ws.app.state.conn_manager.broadcast(payload))
    else:
        # Direct send for browser WebSocket
        try:
            await ws.send_json(payload)
        except Exception as e:
            logger.debug("Failed to send tool frame: %s", e)


async def push_tool_start(
    ws: WebSocket,
    tool_name: str,
    call_id: str,
    arguments: dict[str, Any],
    *,
    is_acs: bool = False,
    session_id: str | None = None,
) -> None:
    """
    Emit tool_start event when a tool begins execution.

    Args:
        ws: WebSocket connection
        tool_name: Name of the tool being called
        call_id: Unique ID for this tool invocation
        arguments: Tool arguments
        is_acs: Whether this is an ACS call (broadcast) or browser (direct)
        session_id: Session ID for session-aware broadcasting
    """
    payload = {
        "type": "tool_start",
        "tool": tool_name,
        "call_id": call_id,
        "arguments": arguments,
        "timestamp": time.time(),
        "session_id": session_id,
    }
    await _emit(ws, payload, is_acs=is_acs, session_id=session_id)


def _derive_tool_status(result: Any) -> str:
    """
    Derive success/error status from tool result.

    Convention: A tool result dict with `success: False` or `error` key
    is considered a failure. Everything else is success.
    """
    if isinstance(result, dict):
        # Explicit success=False means failure
        if result.get("success") is False:
            return "error"
        # Presence of "error" key (without success=True) means failure
        if "error" in result and result.get("success") is not True:
            return "error"
    return "success"


async def push_tool_end(
    ws: WebSocket,
    tool_name: str,
    call_id: str,
    result: Any,
    *,
    is_acs: bool = False,
    session_id: str | None = None,
    duration_ms: float | None = None,
) -> None:
    """
    Emit tool_end event when a tool completes execution.

    Args:
        ws: WebSocket connection
        tool_name: Name of the tool that completed
        call_id: Unique ID for this tool invocation
        result: Tool execution result
        is_acs: Whether this is an ACS call (broadcast) or browser (direct)
        session_id: Session ID for session-aware broadcasting
        duration_ms: Optional execution duration in milliseconds
    """
    status = _derive_tool_status(result)
    serialized_result = _safe_serialize(result)

    # Extract error message for failed tools
    error_msg = None
    if status == "error" and isinstance(result, dict):
        error_msg = result.get("error") or result.get("message") or "Tool execution failed"

    payload = {
        "type": "tool_end",
        "tool": tool_name,
        "call_id": call_id,
        "status": status,
        "result": serialized_result,
        "timestamp": time.time(),
        "session_id": session_id,
    }
    if error_msg:
        payload["error"] = error_msg
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms

    await _emit(ws, payload, is_acs=is_acs, session_id=session_id)


async def push_tool_progress(
    ws: WebSocket,
    tool_name: str,
    call_id: str,
    message: str,
    *,
    is_acs: bool = False,
    session_id: str | None = None,
) -> None:
    """
    Emit tool_progress event for long-running tools.

    Args:
        ws: WebSocket connection
        tool_name: Name of the tool
        call_id: Unique ID for this tool invocation
        message: Progress message
        is_acs: Whether this is an ACS call (broadcast) or browser (direct)
        session_id: Session ID for session-aware broadcasting
    """
    payload = {
        "type": "tool_progress",
        "tool": tool_name,
        "call_id": call_id,
        "message": message,
        "timestamp": time.time(),
        "session_id": session_id,
    }
    await _emit(ws, payload, is_acs=is_acs, session_id=session_id)


def _safe_serialize(value: Any) -> Any:
    """Safely serialize a value for JSON."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _safe_serialize(v) for k, v in value.items()}
    try:
        return str(value)
    except Exception:
        return "<unserializable>"


__all__ = [
    "push_tool_start",
    "push_tool_end",
    "push_tool_progress",
]
