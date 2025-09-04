from __future__ import annotations

import json
from typing import Any, Dict, TYPE_CHECKING

from fastapi import WebSocket

from .bindings import get_agent_instance
from .cm_utils import cm_get, cm_set, get_correlation_context
from .config import LAST_ANNOUNCED_KEY, APP_GREETS_ATTR
from apps.rtagent.backend.src.ws_helpers.shared_ws import (
    broadcast_message,
    send_tts_audio,
    send_response_to_acs,
)
from apps.rtagent.backend.src.ws_helpers.envelopes import make_status_envelope
from utils.ml_logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from src.stateful.state_managment import MemoManager


def sync_voice_from_agent(cm: "MemoManager", ws: WebSocket, agent_name: str) -> None:
    """
    Update CoreMemory voice fields based on the agent instance.
    """
    agent = get_agent_instance(ws, agent_name)
    voice_name = getattr(agent, "voice_name", None) if agent else None
    voice_style = getattr(agent, "voice_style", "chat") if agent else "chat"
    voice_rate = getattr(agent, "voice_rate", "+3%") if agent else "+3%"
    cm_set(
        cm,
        current_agent_voice=voice_name,
        current_agent_voice_style=voice_style,
        current_agent_voice_rate=voice_rate,
    )


async def send_agent_greeting(
    cm: "MemoManager", ws: WebSocket, agent_name: str, is_acs: bool
) -> None:
    """
    Emit a greeting when switching to a specialist agent (behavior-preserving).
    """
    if cm is None:
        logger.error("MemoManager is None in send_agent_greeting for agent=%s", agent_name)
        return

    if agent_name == cm_get(cm, LAST_ANNOUNCED_KEY):
        return  # prevent duplicate greeting

    agent = get_agent_instance(ws, agent_name)
    voice_name = getattr(agent, "voice_name", None) if agent else None
    voice_style = getattr(agent, "voice_style", "chat") if agent else "chat"
    voice_rate = getattr(agent, "voice_rate", "+3%") if agent else "+3%"
    actual_agent_name = getattr(agent, "name", None) or agent_name

    state_counts: Dict[str, int] = getattr(ws.state, APP_GREETS_ATTR, {})
    if not hasattr(ws.state, APP_GREETS_ATTR):
        ws.state.__setattr__(APP_GREETS_ATTR, state_counts)

    counter = state_counts.get(actual_agent_name, 0)
    state_counts[actual_agent_name] = counter + 1

    caller_name = cm_get(cm, "caller_name")
    topic = cm_get(cm, "topic") or cm_get(cm, "claim_intent") or "your policy"

    if counter == 0:
        greeting = (
            f"Hi {caller_name}, this is the {agent_name} specialist agent. "
            f"I understand you're calling about {topic}. How can I help you further?"
        )
    else:
        greeting = (
            f"Welcome back, {caller_name}. {agent_name} specialist here. "
            f"What else can I assist you with?"
        )

    cm.append_to_history(actual_agent_name, "assistant", greeting)
    cm_set(cm, **{LAST_ANNOUNCED_KEY: agent_name})

    if is_acs:
        logger.info("ACS greeting #%s for %s (voice: %s): %s", counter + 1, agent_name, voice_name or "default", greeting)
        if agent_name == "Claims":
            agent_sender = "Claims Specialist"
        elif agent_name == "General":
            agent_sender = "General Info"
        else:
            agent_sender = "Assistant"

        _, session_id = get_correlation_context(ws, cm)
        await broadcast_message(None, greeting, agent_sender, app_state=ws.app.state, session_id=session_id)
        try:
            await send_response_to_acs(
                ws=ws,
                text=greeting,
                blocking=False,
                latency_tool=ws.state.lt,
                voice_name=voice_name,
                voice_style=voice_style,
                rate=voice_rate,
            )
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to send ACS greeting audio: %s", exc)
            logger.warning("ACS greeting sent as text only.")
    else:
        logger.info("WS greeting #%s for %s (voice: %s)", counter + 1, agent_name, voice_name or "default")
        _, session_id = get_correlation_context(ws, cm)
        envelope = make_status_envelope(message=greeting, session_id=session_id)
        if hasattr(ws.app.state, "conn_manager") and hasattr(ws.state, "conn_id"):
            await ws.app.state.conn_manager.send_to_connection(ws.state.conn_id, envelope)
        else:
            await ws.send_text(json.dumps({"type": "status", "message": greeting}))
        await send_tts_audio(
            greeting,
            ws,
            latency_tool=ws.state.lt,
            voice_name=voice_name,
            voice_style=voice_style,
            rate=voice_rate,
        )
