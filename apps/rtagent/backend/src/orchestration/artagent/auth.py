from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from fastapi import WebSocket

from .bindings import get_agent_instance
from .cm_utils import cm_get, cm_set
from .greetings import send_agent_greeting, sync_voice_from_agent
from .latency import track_latency
from utils.ml_logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from src.stateful.state_managment import MemoManager


async def run_auth_agent(
    cm: "MemoManager",
    utterance: str,
    ws: WebSocket,
    *,
    is_acs: bool,
) -> None:
    """
    Run the AutoAuth agent once per session until authenticated.
    """
    if cm is None:
        logger.error("MemoManager is None in run_auth_agent")
        raise ValueError("MemoManager (cm) parameter cannot be None in run_auth_agent")

    auth_agent = get_agent_instance(ws, "AutoAuth")

    async with track_latency(ws.state.lt, "auth_agent", ws.app.state.redis, meta={"agent": "AutoAuth"}):
        result: Dict[str, Any] | Any = await auth_agent.respond(  # type: ignore[union-attr]
            cm, utterance, ws, is_acs=is_acs
        )

    if isinstance(result, dict) and result.get("handoff") == "human_agent":
        reason = result.get("reason") or result.get("escalation_reason")
        cm_set(cm, escalated=True, escalation_reason=reason)
        logger.warning("Escalation during auth – session=%s reason=%s", cm.session_id, reason)
        return

    if isinstance(result, dict) and result.get("authenticated"):
        caller_name: str | None = result.get("caller_name")
        policy_id: str | None = result.get("policy_id")
        claim_intent: str | None = result.get("claim_intent")
        topic: str | None = result.get("topic")
        intent: str = result.get("intent", "general")
        active_agent: str = "Claims" if intent == "claims" else "General"

        cm_set(
            cm,
            authenticated=True,
            caller_name=caller_name,
            policy_id=policy_id,
            claim_intent=claim_intent,
            topic=topic,
            active_agent=active_agent,
        )

        logger.info(
            "Auth OK – session=%s caller=%s policy=%s → %s agent",
            cm.session_id,
            caller_name,
            policy_id,
            active_agent,
        )

        sync_voice_from_agent(cm, ws, active_agent)
        await send_agent_greeting(cm, ws, active_agent, is_acs)
