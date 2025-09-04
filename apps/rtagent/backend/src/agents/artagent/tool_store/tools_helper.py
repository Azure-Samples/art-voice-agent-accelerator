"""
tools_helper.py

Single source of truth for
 • callable-name → python-function mapping
 • JSON frames that announce tool_start / tool_progress / tool_end
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Callable, Dict, Optional

from utils.ml_logging import get_logger

logger = get_logger(__name__)

from fastapi import WebSocket

from apps.rtagent.backend.src.agents.artagent.tool_store.tool_registry import function_mapping
from utils.ml_logging import get_logger

log = get_logger("tools_helper")


async def call_agent_tool(tool_name: str, args: dict) -> Any:
    fn = function_mapping.get(tool_name)
    if fn is None:
        log.error(f"No function mapped for tool '{tool_name}'")
        return {"ok": False, "message": f"Tool '{tool_name}' not supported."}
    try:
        result = await fn(args)
        return result
    except Exception as e:
        log.exception(f"Error running tool '{tool_name}'")
        return {"ok": False, "message": str(e)}


async def _emit(
    ws: WebSocket, payload: dict, *, is_acs: bool, session_id: Optional[str] = None
) -> None:
    """
    • browser `/realtime`  → send JSON directly to specific session
    • phone   `/call/*`    → broadcast to dashboards only for that session

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
                    f"Tool frame broadcasted to session {session_id}: {payload.get('tool', 'unknown')}"
                )
            else:
                # Fallback: Dashboard-only broadcast (safer than broadcast_all)
                asyncio.create_task(
                    ws.app.state.conn_manager.broadcast_topic("dashboard", payload)
                )
                logger.warning(
                    f"Tool frame broadcasted to dashboard topic (no session): {payload.get('tool', 'unknown')}"
                )
        else:
            logger.warning("ConnectionManager not available for tool frame broadcast")
    else:
        # Direct WebSocket send for browser connections
        frame = json.dumps(payload)
        await ws.send_text(frame)


def _frame(
    _type: str,
    call_id: str,
    name: str,
    **extra: Any,
) -> dict:
    return {
        "type": _type,
        "callId": call_id,
        "tool": name,
        "ts": time.time(),
        **extra,
    }


async def push_tool_start(
    ws: WebSocket,
    call_id: str,
    name: str,
    args: dict,
    *,
    is_acs: bool = False,
    session_id: Optional[str] = None,
) -> None:
    await _emit(
        ws,
        _frame("tool_start", call_id, name, args=args),
        is_acs=is_acs,
        session_id=session_id,
    )


async def push_tool_progress(
    ws: WebSocket,
    call_id: str,
    name: str,
    pct: int,
    note: str | None = None,
    *,
    is_acs: bool = False,
    session_id: Optional[str] = None,
) -> None:
    await _emit(
        ws,
        _frame("tool_progress", call_id, name, pct=pct, note=note),
        is_acs=is_acs,
        session_id=session_id,
    )


async def push_tool_end(
    ws: WebSocket,
    call_id: str,
    name: str,
    status: str,  # "success" | "error"
    elapsed_ms: float,
    *,
    result: dict | None = None,
    error: str | None = None,
    is_acs: bool = False,
    session_id: Optional[str] = None,
) -> None:
    await _emit(
        ws,
        _frame(
            "tool_end",
            call_id,
            name,
            status=status,
            elapsedMs=round(elapsed_ms, 1),
            result=result,
            error=error,
        ),
        is_acs=is_acs,
        session_id=session_id,
    )
