from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from fastapi import WebSocket

from .bindings import get_agent_instance
from .cm_utils import cm_set, get_correlation_context
from .greetings import send_agent_greeting, sync_voice_from_agent
from .latency import track_latency
from apps.rtagent.backend.src.services.acs.session_terminator import (
    TerminationReason,
    terminate_session,
)
from utils.ml_logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from src.stateful.state_managment import MemoManager


def _extract_voicemail_payload(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize voicemail detection payloads from tool responses."""
    if not isinstance(result, dict):
        return None

    if result.get("voicemail_detected"):
        return result

    data = result.get("data")
    if isinstance(data, dict) and data.get("voicemail_detected"):
        return data
    return None


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

    voicemail_payload = _extract_voicemail_payload(result) if isinstance(result, dict) else None
    if voicemail_payload and voicemail_payload.get("voicemail_detected"):
        summary = voicemail_payload.get("summary") or voicemail_payload.get("voicemail_cues")
        confidence = voicemail_payload.get("confidence")

        cm_set(
            cm,
            voicemail_detected=True,
            voicemail_summary=summary,
            voicemail_confidence=confidence,
        )

        call_connection_id, _ = get_correlation_context(ws, cm)
        logger.info(
            "Voicemail detected – ending session. session=%s confidence=%s",
            cm.session_id,
            confidence,
        )
        await terminate_session(
            ws,
            is_acs=is_acs,
            call_connection_id=call_connection_id if is_acs else None,
            reason=TerminationReason.VOICEMAIL,
        )
        return

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
