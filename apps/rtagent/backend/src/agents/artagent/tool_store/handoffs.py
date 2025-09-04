from __future__ import annotations

"""
FNOL voice-agent *escalation and hand-off* utilities.

This module exposes **three** async callables that the LLM can invoke
to redirect the conversation flow:

1. ``handoff_general_agent`` – transfer to the *General Insurance Questions*
   AI agent whenever the caller seeks broad, non-claim-specific information
   (e.g., “What is covered under comprehensive?”).
2. ``handoff_claim_agent`` – transfer to the *Claims Intake* AI agent when
   the caller wants to start or update a claim.
3. ``escalate_human`` – cold-transfer to a live adjuster for fraud flags,
   repeated validation loops, backend errors, or customer frustration.

All functions follow project standards (PEP 8 typing, structured logging,
robust error handling, and JSON responses via ``_json``).
"""

from datetime import datetime, timezone
from typing import Any, Dict, TypedDict

from apps.rtagent.backend.src.agents.artagent.tool_store.functions_helper import _json
from utils.ml_logging import get_logger

logger = get_logger("fnol_escalations")


# ────────────────────────────────────────────────────────────────
# General-info hand-off
# ────────────────────────────────────────────────────────────────
class HandoffGeneralArgs(TypedDict):
    """Input schema for :pyfunc:`handoff_general_agent`."""

    topic: str  # e.g. "coverage", "billing"
    caller_name: str


async def handoff_general_agent(args: HandoffGeneralArgs) -> Dict[str, Any]:
    """
    Transfer the caller to the **General Insurance Questions** AI agent.
    """
    # Input type validation to prevent 400 errors
    if not isinstance(args, dict):
        logger.error("Invalid args type: %s. Expected dict.", type(args))
        return _json(False, "Invalid request format. Please provide handoff details.")
    
    try:
        topic = args.get("topic", "").strip()
        caller_name = args.get("caller_name", "").strip()

        if not topic or not caller_name:
            return _json(False, "Both 'topic' and 'caller_name' must be provided.")

        logger.info(
            "🤖 Hand-off to General-Info agent – topic=%s caller=%s", topic, caller_name
        )
        return _json(
            True,
            "Caller transferred to General Insurance Questions agent.",
            handoff="ai_agent",
            target_agent="General Insurance Questions",
            topic=topic,
        )
    except Exception as exc:
        # Catch all exceptions to prevent 400 errors
        logger.error("General handoff failed: %s", exc, exc_info=True)
        return _json(False, "Technical error during handoff. Please try again.")


# ────────────────────────────────────────────────────────────────
# Claims-intake hand-off  🆕
# ────────────────────────────────────────────────────────────────
class HandoffClaimArgs(TypedDict):
    """Input schema for :pyfunc:`handoff_claim_agent`."""

    caller_name: str
    policy_id: str
    claim_intent: str  # e.g. "new_claim", "update_claim"


async def handoff_claim_agent(args: HandoffClaimArgs) -> Dict[str, Any]:
    """
    Transfer the caller to the **Claims Intake** AI agent.

    Parameters
    ----------
    caller_name : str
    policy_id   : str
    claim_intent: str   (free-text hint such as "new_claim")
    """
    # Input type validation to prevent 400 errors
    if not isinstance(args, dict):
        logger.error("Invalid args type: %s. Expected dict.", type(args))
        return _json(False, "Invalid request format. Please provide claim handoff details.")
    
    try:
        caller_name = args.get("caller_name", "").strip()
        policy_id = args.get("policy_id", "").strip()
        intent = args.get("claim_intent", "").strip()

        if not caller_name or not policy_id:
            return _json(
                False, "'caller_name' and 'policy_id' are required for claim hand-off."
            )

        logger.info(
            "📂 Hand-off to Claims agent – %s (%s) intent=%s",
            caller_name,
            policy_id,
            intent or "n/a",
        )

        return _json(
            True,
            "Caller transferred to Claims Intake agent.",
            handoff="ai_agent",
            target_agent="Claims Intake",
            claim_intent=intent or "unspecified",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        # Catch all exceptions to prevent 400 errors
        logger.error("Claim handoff failed: %s", exc, exc_info=True)
        return _json(False, "Technical error during claim handoff. Please try again.")


# ────────────────────────────────────────────────────────────────
# Human escalation
# ────────────────────────────────────────────────────────────────
class EscalateHumanArgs(TypedDict):
    """Input schema for :pyfunc:`escalate_human`."""

    route_reason: str  # e.g. "validation_loop", "backend_error", "fraud_flags"
    caller_name: str
    policy_id: str


async def escalate_human(args: EscalateHumanArgs) -> Dict[str, Any]:
    """
    Escalate *non-emergency* scenarios to a human insurance adjuster.
    """
    # Input type validation to prevent 400 errors
    if not isinstance(args, dict):
        logger.error("Invalid args type: %s. Expected dict.", type(args))
        return _json(False, "Invalid request format. Please provide escalation details.")
    
    try:
        route_reason = args.get("route_reason", "").strip()
        caller_name = args.get("caller_name", "").strip()
        policy_id = args.get("policy_id", "").strip()
        
        # Check for missing required fields
        if not route_reason:
            return _json(False, "'route_reason' is required for human escalation.")
        if not caller_name:
            return _json(False, "'caller_name' is required for human escalation.")
        if not policy_id:
            return _json(False, "'policy_id' is required for human escalation.")

        logger.info(
            "🤝 Human hand-off – %s (%s) reason=%s", caller_name, policy_id, route_reason
        )
        return _json(
            True,
            "Caller transferred to human insurance agent.",
            handoff="human_agent",
            route_reason=route_reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        # Catch all exceptions to prevent 400 errors
        logger.error("Human escalation failed: %s", exc, exc_info=True)
        return _json(False, "Technical error during human escalation. Please try again.")