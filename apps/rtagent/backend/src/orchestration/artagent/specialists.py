from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from fastapi import WebSocket

from .cm_utils import cm_get
from .greetings import send_agent_greeting
from .latency import track_latency
from .bindings import get_agent_instance
from .tools import process_tool_response
from utils.ml_logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from src.stateful.state_managment import MemoManager


async def _run_specialist_base(
    *,
    agent_key: str,
    cm: "MemoManager",
    utterance: str,
    ws: WebSocket,
    is_acs: bool,
    context_message: str,
    respond_kwargs: Dict[str, Any],
    latency_label: str,
) -> None:
    """
    Shared runner for specialist agents (behavior-preserving).
    """
    agent = get_agent_instance(ws, agent_key)

    cm.append_to_history(getattr(agent, "name", agent_key), "assistant", context_message)

    async with track_latency(ws.state.lt, latency_label, ws.app.state.redis, meta={"agent": agent_key}):
        resp = await agent.respond(  # type: ignore[union-attr]
            cm,
            utterance,
            ws,
            is_acs=is_acs,
            **respond_kwargs,
        )

    await process_tool_response(cm, resp, ws, is_acs)


async def run_general_agent(
    cm: "MemoManager",
    utterance: str,
    ws: WebSocket,
    *,
    is_acs: bool,
) -> None:
    """
    Handle a turn with the GeneralInfoAgent.
    """
    if cm is None:
        logger.error("MemoManager is None in run_general_agent")
        raise ValueError("MemoManager (cm) parameter cannot be None in run_general_agent")

    caller_name = cm_get(cm, "caller_name")
    topic = cm_get(cm, "topic")
    policy_id = cm_get(cm, "policy_id")

    context_msg = f"Authenticated caller: {caller_name} (Policy: {policy_id}) | Topic: {topic}"
    await _run_specialist_base(
        agent_key="General",
        cm=cm,
        utterance=utterance,
        ws=ws,
        is_acs=is_acs,
        context_message=context_msg,
        respond_kwargs={"caller_name": caller_name, "topic": topic, "policy_id": policy_id},
        latency_label="general_agent",
    )


async def run_claims_agent(
    cm: "MemoManager",
    utterance: str,
    ws: WebSocket,
    *,
    is_acs: bool,
) -> None:
    """
    Handle a turn with the ClaimIntakeAgent.
    """
    if cm is None:
        logger.error("MemoManager is None in run_claims_agent")
        raise ValueError("MemoManager (cm) parameter cannot be None in run_claims_agent")

    caller_name = cm_get(cm, "caller_name")
    claim_intent = cm_get(cm, "claim_intent")
    policy_id = cm_get(cm, "policy_id")

    context_msg = (
        f"Authenticated caller: {caller_name} (Policy: {policy_id}) | Claim Intent: {claim_intent}"
    )
    await _run_specialist_base(
        agent_key="Claims",
        cm=cm,
        utterance=utterance,
        ws=ws,
        is_acs=is_acs,
        context_message=context_msg,
        respond_kwargs={"caller_name": caller_name, "claim_intent": claim_intent, "policy_id": policy_id},
        latency_label="claim_agent",
    )
