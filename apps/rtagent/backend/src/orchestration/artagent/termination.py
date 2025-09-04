from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import WebSocket

from .cm_utils import cm_get, get_correlation_context
from apps.rtagent.backend.src.services.acs.session_terminator import (
    terminate_session,
    TerminationReason,
)
from apps.rtagent.backend.src.ws_helpers.envelopes import make_event_envelope
from utils.ml_logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from src.stateful.state_managment import MemoManager


async def maybe_terminate_if_escalated(cm: "MemoManager", ws: WebSocket, *, is_acs: bool) -> bool:
    """
    If CoreMemory shows `escalated=True`, notify frontend and terminate the session.

    :param cm: MemoManager
    :param ws: WebSocket
    :param is_acs: Whether this is an ACS call context
    :return: True if termination was performed; False otherwise
    """
    if not cm_get(cm, "escalated", False):
        return False

    try:
        _, session_id = get_correlation_context(ws, cm)
        envelope = make_event_envelope(
            event_type="live_agent_transfer",
            event_data={"type": "live_agent_transfer"},
            session_id=session_id,
        )
        if hasattr(ws.app.state, "conn_manager") and hasattr(ws.state, "conn_id"):
            await ws.app.state.conn_manager.send_to_connection(ws.state.conn_id, envelope)
        else:
            await ws.send_text(json.dumps({"type": "live_agent_transfer"}))
    except Exception:  # pragma: no cover
        pass

    call_connection_id, _ = get_correlation_context(ws, cm)
    await terminate_session(
        ws,
        is_acs=is_acs,
        call_connection_id=call_connection_id,
        reason=TerminationReason.HUMAN_HANDOFF,
    )
    return True
