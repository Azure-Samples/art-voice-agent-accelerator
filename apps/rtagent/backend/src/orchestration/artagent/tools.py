from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from fastapi import WebSocket

from .cm_utils import cm_get, cm_set
from .greetings import send_agent_greeting, sync_voice_from_agent
from .registry import get_specialist
from .config import SPECIALISTS
from utils.ml_logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from src.stateful.state_managment import MemoManager


def _get_field(resp: Dict[str, Any], key: str) -> Any:
    """
    Return resp[key] or resp['data'][key] if nested.
    """
    if key in resp:
        return resp[key]
    return resp.get("data", {}).get(key) if isinstance(resp.get("data"), dict) else None


async def process_tool_response(cm: "MemoManager", resp: Any, ws: WebSocket, is_acs: bool) -> None:
    """
    Inspect structured tool outputs and update core-memory accordingly.

    Behavior-preserving port of the original _process_tool_response.
    """
    if cm is None:
        logger.error("MemoManager is None in process_tool_response")
        return

    if not isinstance(resp, dict):
        return

    prev_agent: str | None = cm_get(cm, "active_agent")

    handoff_type = _get_field(resp, "handoff")
    target_agent = _get_field(resp, "target_agent")

    claim_success = resp.get("claim_success")
    topic = _get_field(resp, "topic")
    claim_intent = _get_field(resp, "claim_intent")
    intent = _get_field(resp, "intent")

    # Unified intent routing (post-auth)
    if intent in {"claims", "general"} and cm_get(cm, "authenticated", False):
        new_agent: str = "Claims" if intent == "claims" else "General"
        cm_set(cm, active_agent=new_agent, claim_intent=claim_intent, topic=topic)
        sync_voice_from_agent(cm, ws, new_agent)
        if new_agent != prev_agent:
            logger.info("Routed via intent → %s", new_agent)
            await send_agent_greeting(cm, ws, new_agent, is_acs)
        return

    # Hand-offs (non-auth)
    if handoff_type == "ai_agent" and target_agent:
        if target_agent in SPECIALISTS or get_specialist(target_agent) is not None:
            new_agent = target_agent
        elif "Claim" in target_agent:
            new_agent = "Claims"
        else:
            new_agent = "General"

        if new_agent == "Claims":
            cm_set(cm, active_agent=new_agent, claim_intent=claim_intent)
        else:
            cm_set(cm, active_agent=new_agent, topic=topic)

        sync_voice_from_agent(cm, ws, new_agent)
        logger.info("Hand-off → %s", new_agent)
        if new_agent != prev_agent:
            await send_agent_greeting(cm, ws, new_agent, is_acs)

    elif handoff_type == "human_agent":
        reason = _get_field(resp, "reason") or _get_field(resp, "escalation_reason")
        cm_set(cm, escalated=True, escalation_reason=reason)

    elif claim_success:
        cm_set(cm, intake_completed=True, latest_claim_id=resp["claim_id"])  # type: ignore[index]
